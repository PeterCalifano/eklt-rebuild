/// @file tracker.cpp
/// @brief Implements the thin ROS1 interface for native EKLT orchestration.
/// @details Callbacks convert ROS storage into owning native inputs. One
///          bounded worker serializes those inputs through the ROS-free state
///          machine and adapts only its emitted tracks and snapshots.

#include "tracker.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <utility>

#include <cv_bridge/cv_bridge.h>
#include <glog/logging.h>
#include <sensor_msgs/image_encodings.h>

#include "flags.h"
#include "tracker_utils.h"

namespace tracker
{
    namespace
    {

        /// @brief Convert a configured second offset to native microseconds.
        /// @param seconds Nonnegative seconds, or a negative disabled sentinel.
        /// @return Truncated microseconds, or `-1` for a negative input.
        /// @throws std::invalid_argument If the value is non-finite or exceeds
        ///         the native timestamp representation.
        int64_t SecondsToUs(double seconds)
        {
            if (!std::isfinite(seconds))
            {
                throw std::invalid_argument("ROS1 first_image_t must be finite");
            }
            if (seconds < 0.0)
            {
                return -1;
            }

            const long double timestamp_us = static_cast<long double>(seconds) * 1000000.0L;
            if (timestamp_us > static_cast<long double>(std::numeric_limits<int64_t>::max()))
            {
                throw std::invalid_argument("ROS1 first_image_t exceeds native timestamp range");
            }
            return static_cast<int64_t>(timestamp_us);
        }

        /// @brief Add an event count without wrapping viewer scheduling state.
        /// @param value Current count.
        /// @param increment Accepted input count.
        /// @return Saturated sum.
        std::size_t SaturatingAdd(std::size_t value, std::size_t increment)
        {
            const std::size_t maximum = std::numeric_limits<std::size_t>::max();
            if (increment > maximum - value)
            {
                return maximum;
            }
            return value + increment;
        }

    } // namespace

    Tracker::Tracker(ros::NodeHandle &nh, viewer::Viewer &viewer)
        : nh_(nh), image_transport_(nh), viewer_ptr_(&viewer)
    {
        validateFlags();

        if (!FLAGS_tracks_file_txt.empty())
        {
            tracks_file_.open(FLAGS_tracks_file_txt);
            if (!tracks_file_.is_open())
            {
                LOG(ERROR) << "Failed to open tracks file '" << FLAGS_tracks_file_txt << "'.";
            }
        }

        event_sub_ = nh_.subscribe("events", 10, &Tracker::eventsCallback, this);
        if (!FLAGS_event_only_mode)
        {
            image_sub_ = image_transport_.subscribe("images", 1, &Tracker::imageCallback, this);
        }
        input_processing_thread_ = std::thread(&Tracker::processInputs, this);
    }

    Tracker::~Tracker()
    {
        stop_requested_.store(true);
        event_sub_.shutdown();
        image_sub_.shutdown();
        inputs_condition_.notify_all();

        if (input_processing_thread_.joinable())
        {
            input_processing_thread_.join();
        }
        if (tracks_file_.is_open())
        {
            tracks_file_.close();
        }
    }

    void Tracker::validateFlags() const
    {
        if (!std::isfinite(FLAGS_scale) || FLAGS_scale <= 0.0 ||
            !std::isfinite(FLAGS_arrow_length) || FLAGS_arrow_length < 0.0)
        {
            throw std::invalid_argument("ROS1 viewer scale and arrow length are invalid");
        }

        // Construct one compact valid geometry so the canonical native
        // validator remains the single source of tracking invariants.
        const eklt_core::SEkltTrackerConfig config = makeConfig(64, 64);
        const eklt_core::CEkltTrackerOrchestrator validated_tracker(config);
        (void)validated_tracker;
    }

    eklt_core::SEkltTrackerConfig Tracker::makeConfig(int width, int height) const
    {
        eklt_core::SEkltTrackerConfig config;
        config.width = width;
        config.height = height;
        config.initialization_mode = FLAGS_event_only_mode
                                         ? eklt_core::ETrackerInitializationMode::EventOnlyFibar
                                         : eklt_core::ETrackerInitializationMode::FrameBacked;
        if (FLAGS_bootstrap == "klt")
        {
            config.bootstrap_mode = eklt_core::ETrackerBootstrapMode::Klt;
        }
        else if (FLAGS_bootstrap == "events")
        {
            config.bootstrap_mode = eklt_core::ETrackerBootstrapMode::Events;
        }
        else
        {
            throw std::invalid_argument("ROS1 bootstrap must be either 'klt' or 'events'");
        }

        config.max_corners = FLAGS_max_corners;
        config.min_corners = FLAGS_min_corners;
        config.min_distance = FLAGS_min_distance;
        config.quality_level = FLAGS_quality_level;
        config.block_size = FLAGS_block_size;
        config.harris_k = FLAGS_k;
        config.patch_size = FLAGS_patch_size;
        config.batch_size = FLAGS_batch_size;
        config.update_every_n_events = FLAGS_update_every_n_events;
        config.max_num_iterations = FLAGS_max_num_iterations;
        config.lk_window_size = FLAGS_lk_window_size;
        config.num_pyramidal_layers = FLAGS_num_pyramidal_layers;
        config.displacement_px = FLAGS_displacement_px;
        config.tracking_quality = FLAGS_tracking_quality;
        config.log_eps = FLAGS_log_eps;
        config.first_image_t_us = SecondsToUs(FLAGS_first_image_t);
        config.reconstruction_interval_events = FLAGS_event_only_reconstruction_interval_events;
        config.fibar_cutoff_time_us = FLAGS_fibar_cutoff_time_us;
        config.fibar_fill_ratio = FLAGS_fibar_fill_ratio;
        config.fibar_use_spatial_filter = FLAGS_fibar_use_spatial_filter;
        return config;
    }

    void Tracker::queueInput(SQueuedInput input)
    {
        std::unique_lock<std::mutex> lock(inputs_mutex_);
        inputs_condition_.wait(lock,
                               [this]()
                               {
                                   return stop_requested_.load() ||
                                          inputs_.size() < kMaxQueuedInputs;
                               });
        if (stop_requested_.load())
        {
            return;
        }

        // Bound transport-owned copies independently of event rate. Backpressure
        // leaves ROS subscription queues responsible for upstream buffering.
        inputs_.push_back(std::move(input));
        lock.unlock();
        inputs_condition_.notify_all();
    }

    void Tracker::processInputs()
    {
        while (true)
        {
            SQueuedInput input;
            {
                std::unique_lock<std::mutex> lock(inputs_mutex_);
                inputs_condition_.wait(lock, [this]()
                                       { return stop_requested_.load() || !inputs_.empty(); });
                if (stop_requested_.load() && inputs_.empty())
                {
                    return;
                }

                input = std::move(inputs_.front());
                inputs_.pop_front();
            }
            inputs_condition_.notify_all();

            try
            {
                processInput(std::move(input));
            }
            catch (const std::exception &exception)
            {
                LOG(ERROR) << "Native EKLT rejected a ROS1 input batch: " << exception.what();
            }
        }
    }

    bool Tracker::ensureOrchestrator(int width, int height)
    {
        if (width <= 0 || height <= 0)
        {
            LOG(ERROR) << "Ignoring ROS1 input with nonpositive geometry " << width << "x" << height
                       << ".";
            return false;
        }
        if (!orchestrator_)
        {
            orchestrator_ =
                std::make_unique<eklt_core::CEkltTrackerOrchestrator>(makeConfig(width, height));
            return true;
        }
        if (orchestrator_->config().width != width || orchestrator_->config().height != height)
        {
            LOG(ERROR) << "Ignoring ROS1 input whose geometry changed from "
                       << orchestrator_->config().width << "x" << orchestrator_->config().height
                       << " to " << width << "x" << height << ".";
            return false;
        }
        return true;
    }

    void Tracker::processInput(SQueuedInput input)
    {
        if (!ensureOrchestrator(input.width, input.height))
        {
            return;
        }

        const bool was_initialized = orchestrator_->initialized();
        bool accepted = false;
        std::size_t accepted_event_count = 0;
        if (input.kind == EInputKind::Frame)
        {
            accepted = orchestrator_->acceptFrame(input.frame);
        }
        else
        {
            accepted_event_count = input.events.size();
            accepted = orchestrator_->acceptEvents(std::move(input.events));
        }
        if (!accepted)
        {
            VLOG_EVERY_N(1, 30) << "Native EKLT deferred or rejected one ROS1 input.";
            return;
        }

        const bool is_initialized = orchestrator_->initialized();
        if (!FLAGS_event_only_mode && is_initialized)
        {
            ready_for_frame_events_.store(true);
        }

        // Serialize only rows emitted by the native state machine so file
        // output and generated wrappers observe the same feature history.
        writeTracks(orchestrator_->takeTrackSamples());
        events_since_view_ = SaturatingAdd(events_since_view_, accepted_event_count);
        publishSnapshot(!was_initialized && is_initialized);
    }

    void Tracker::writeTracks(const std::vector<eklt_core::STrackSample> &samples)
    {
        if (!tracks_file_.is_open())
        {
            return;
        }

        for (const eklt_core::STrackSample &sample : samples)
        {
            tracks_file_ << sample.id << " " << std::setprecision(15)
                         << static_cast<double>(sample.t_us) / 1000000.0 << " " << sample.center.x
                         << " " << sample.center.y << "\n";
        }
        tracks_file_.flush();
    }

    void Tracker::publishSnapshot(bool force)
    {
        if (!FLAGS_display_features || !orchestrator_ || !orchestrator_->initialized())
        {
            return;
        }

        const std::size_t update_interval =
            static_cast<std::size_t>(std::max(1, FLAGS_update_every_n_events));
        if (!force && events_since_view_ < update_interval)
        {
            return;
        }

        const eklt_core::STrackerSnapshot snapshot = orchestrator_->snapshot();
        if (!snapshot.valid())
        {
            return;
        }

        const ros::Time snapshot_time = RosTimeFromUs(snapshot.t_us);
        if (!viewer_initialized_)
        {
            viewer_ptr_->initViewData(RosTimeFromUs(snapshot.image.t_us));
            viewer_initialized_ = true;
        }
        viewer_ptr_->setViewData(snapshot, snapshot_time);
        events_since_view_ = 0;
    }

    void Tracker::eventsCallback(const dvs_msgs::EventArray::ConstPtr &msg)
    {
        if (!msg || msg->events.empty())
        {
            return;
        }
        if (!FLAGS_event_only_mode && !ready_for_frame_events_.load())
        {
            LOG_EVERY_N(INFO, 20) << "Events dropped since no initialization image "
                                     "has been accepted.";
            return;
        }

        SQueuedInput input;
        input.kind = EInputKind::Events;
        input.width = static_cast<int>(msg->width);
        input.height = static_cast<int>(msg->height);
        input.events.reserve(msg->events.size());

        // Convert exact integer timestamps and signed polarity at the sole
        // ROS1 boundary; native acceptance owns sorting and validation.
        for (const dvs_msgs::Event &event : msg->events)
        {
            eklt_core::SEventSample sample;
            sample.x = event.x;
            sample.y = event.y;
            sample.p = static_cast<int8_t>(event.polarity ? 1 : -1);
            sample.t_us = RosTimeToUs(event.ts);
            input.events.push_back(sample);
        }
        queueInput(std::move(input));
    }

    void Tracker::imageCallback(const sensor_msgs::Image::ConstPtr &msg)
    {
        if (!msg || FLAGS_event_only_mode)
        {
            return;
        }
        if (msg->header.stamp.toSec() < FLAGS_first_image_t)
        {
            return;
        }

        cv_bridge::CvImagePtr image;
        try
        {
            image = cv_bridge::toCvCopy(msg, sensor_msgs::image_encodings::MONO8);
        }
        catch (const cv_bridge::Exception &exception)
        {
            ROS_ERROR("cv_bridge exception: %s", exception.what());
            return;
        }

        // Move the cv_bridge allocation into one bounded work item. The native
        // boundary clones it before the next transport input can reuse storage.
        SQueuedInput input;
        input.kind = EInputKind::Frame;
        input.width = image->image.cols;
        input.height = image->image.rows;
        input.frame.image = std::move(image->image);
        input.frame.t_us = RosTimeToUs(msg->header.stamp);
        input.frame.width = input.width;
        input.frame.height = input.height;
        input.frame.frame_id = "event_camera";
        queueInput(std::move(input));
    }

} // namespace tracker
