/// @file event_only_eklt_node.cpp
/// @brief Implements the thin ROS2 interface for event-only native EKLT.
/// @details The node owns EventPacket transport, ROS2 parameters, file/topic
///          output, and display-image publication. The ROS-free
///          CEkltTrackerOrchestrator owns reconstruction, scheduling, feature
///          lifecycle, optimization, and gradient-cache release.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>
#include <vector>

#include <event_camera_msgs/msg/event_packet.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/header.hpp>
#include <std_msgs/msg/string.hpp>

#include "eklt_core/image_normalization.h"
#include "eklt_core/tracker_orchestrator.h"
#include "visualization/feature_track_renderer.h"
#include "eklt_rebuild/event_packet_decoder.h"
#include "eklt_rebuild/reconstructed_frame_writer.h"

namespace eklt_rebuild
{
    namespace
    {

        int ReadIntParameter(const rclcpp::Node &node, const char *name)
        {
            const int64_t value = node.get_parameter(name).as_int();
            if (value < static_cast<int64_t>(std::numeric_limits<int>::min()) ||
                value > static_cast<int64_t>(std::numeric_limits<int>::max()))
            {
                throw std::invalid_argument(std::string(name) + " exceeds native integer range");
            }
            return static_cast<int>(value);
        }

        uint32_t ReadUint32Parameter(const rclcpp::Node &node, const char *name)
        {
            const int64_t value = node.get_parameter(name).as_int();
            if (value < 0 ||
                static_cast<uint64_t>(value) >
                    static_cast<uint64_t>(std::numeric_limits<uint32_t>::max()))
            {
                throw std::invalid_argument(std::string(name) + " exceeds uint32 range");
            }
            return static_cast<uint32_t>(value);
        }

        std::size_t ReadSizeParameter(const rclcpp::Node &node, const char *name)
        {
            const int64_t value = node.get_parameter(name).as_int();
            if (value < 0 ||
                static_cast<uint64_t>(value) >
                    static_cast<uint64_t>(std::numeric_limits<std::size_t>::max()))
            {
                throw std::invalid_argument(std::string(name) + " exceeds size range");
            }
            return static_cast<std::size_t>(value);
        }

        std::vector<uint8_t> MakeMono8Image(const cv::Mat &image)
        {
            const cv::Mat normalized = eklt_core::NormalizeImageToUnitRange64(image);
            if (normalized.empty())
            {
                return {};
            }

            cv::Mat mono_image;
            normalized.convertTo(mono_image, CV_8U, 255.0);
            if (!mono_image.isContinuous())
            {
                mono_image = mono_image.clone();
            }
            return std::vector<uint8_t>(mono_image.datastart, mono_image.dataend);
        }

        std::string MakeTrackRow(const eklt_core::STrackSample &sample)
        {
            std::ostringstream row;
            row << sample.id << " " << std::fixed << std::setprecision(9)
                << static_cast<double>(sample.t_us) / 1000000.0 << " "
                << sample.center.x << " " << sample.center.y;
            return row.str();
        }

        std_msgs::msg::Header MakeImageHeader(const std_msgs::msg::Header &packet_header,
                                              int64_t t_us)
        {
            if (t_us < 0 ||
                t_us > std::numeric_limits<int64_t>::max() / 1000)
            {
                throw std::invalid_argument(
                    "snapshot timestamp cannot be represented by a ROS2 header");
            }

            std_msgs::msg::Header image_header = packet_header;
            image_header.stamp = rclcpp::Time(t_us * 1000);
            return image_header;
        }

    } // namespace

    /// @brief Adapt standard ROS2 EventPacket streams to native event-only EKLT.
    /// @details Sensor geometry is fixed by the first valid packet. Subsequent
    ///          packets are synchronously decoded and submitted to one native
    ///          orchestrator, keeping callback memory bounded by the configured
    ///          sensor-data QoS depth.
    class CEventOnlyEkltNode final : public rclcpp::Node
    {
      public:
        /// @brief Construct publishers, parameters, and the EventPacket subscriber.
        CEventOnlyEkltNode() : Node("eklt_rebuild_event_only")
        {
            declareParameters();
            validateInterfaceSelection();
            configureDisplayOutputs();
            openTracksFile(get_parameter("tracks_file_txt").as_string());
            openProcessingTimingFile(get_parameter("processing_timing_file_csv").as_string());

            // Publish only transport-neutral text and image views; reusable
            // snapshots and track structures remain native-library contracts.
            const std::string tracks_topic =
                get_parameter("tracks_topic").as_string();
            const std::string stats_topic =
                get_parameter("stats_topic").as_string();
            const std::string init_debug_image_topic =
                get_parameter("init_debug_image_topic").as_string();
            const std::string feature_tracks_topic =
                get_parameter("feature_tracks_topic").as_string();
            tracks_publisher_ =
                create_publisher<std_msgs::msg::String>(tracks_topic, rclcpp::QoS(10));
            stats_publisher_ =
                create_publisher<std_msgs::msg::String>(stats_topic, rclcpp::QoS(10));
            init_debug_publisher_ =
                create_publisher<sensor_msgs::msg::Image>(init_debug_image_topic,
                                                          rclcpp::SensorDataQoS());
            rclcpp::SensorDataQoS feature_image_qos;
            feature_image_qos.keep_last(1U);
            feature_tracks_publisher_ =
                create_publisher<sensor_msgs::msg::Image>(feature_tracks_topic,
                                                          feature_image_qos);

            const int qos_depth = ReadIntParameter(*this, "events_qos_depth");
            if (qos_depth <= 0)
            {
                throw std::invalid_argument("events_qos_depth must be positive");
            }

            // Bound camera backpressure explicitly so live input cannot turn
            // native tracking latency into unbounded ROS middleware storage.
            rclcpp::SensorDataQoS events_qos;
            events_qos.keep_last(static_cast<std::size_t>(qos_depth));
            const std::string events_topic =
                get_parameter("events_topic").as_string();
            const auto packet_callback =
                [this](event_camera_msgs::msg::EventPacket::ConstSharedPtr packet)
                {
                    handlePacket(*packet);
                };
            event_subscription_ =
                create_subscription<event_camera_msgs::msg::EventPacket>(events_topic,
                                                                         events_qos,
                                                                         packet_callback);
        }

      private:
        void declareParameters()
        {
            declare_parameter<std::string>("events_topic", "/events");
            declare_parameter<int64_t>("events_qos_depth", 4);
            declare_parameter<std::string>("tracks_topic", "/eklt/tracks");
            declare_parameter<std::string>("stats_topic", "/eklt/stats");
            declare_parameter<std::string>("init_debug_image_topic", "/eklt/init_debug_image");
            declare_parameter<std::string>("feature_tracks_topic", "/eklt/feature_tracks");
            declare_parameter<std::string>("tracks_file_txt", "");
            declare_parameter<std::string>("processing_timing_file_csv", "");
            declare_parameter<std::string>("feature_provider", "fibar_harris");
            declare_parameter<std::string>("patch_provider", "fibar");
            declare_parameter<std::string>("bootstrap_mode", "events");
            declare_parameter<bool>("superevent_enabled", false);

            declare_parameter<int64_t>("max_corners", 100);
            declare_parameter<int64_t>("min_corners", 25);
            declare_parameter<double>("min_distance", 10.0);
            declare_parameter<double>("quality_level", 0.01);
            declare_parameter<int64_t>("block_size", 3);
            declare_parameter<double>("harris_k", 0.04);

            declare_parameter<int64_t>("patch_size", 25);
            declare_parameter<int64_t>("batch_size", 300);
            declare_parameter<int64_t>("update_every_n_events", 20);
            declare_parameter<int64_t>("max_num_iterations", 10);
            declare_parameter<double>("tracking_quality", 0.1);
            declare_parameter<double>("displacement_px", 0.6);
            declare_parameter<double>("log_eps", 0.01);
            declare_parameter<int64_t>("first_image_t_us", -1);

            declare_parameter<int64_t>("event_only_reconstruction_interval_events", 5000);
            declare_parameter<int64_t>("fibar_cutoff_time_us", 10000);
            declare_parameter<double>("fibar_fill_ratio", 0.5);
            declare_parameter<bool>("fibar_use_spatial_filter", true);

            declare_parameter<bool>("display_features", true);
            declare_parameter<bool>("display_feature_id", false);
            declare_parameter<bool>("display_feature_patches", false);
            declare_parameter<double>("scale", 4.0);
            declare_parameter<double>("arrow_length", 5.0);
            declare_parameter<double>("visualization_max_rate_hz", 30.0);

            declare_parameter<std::string>("reconstructed_frames_directory", "");
            declare_parameter<int64_t>("reconstructed_frames_stride", 1);
            declare_parameter<int64_t>("reconstructed_frames_max_count", 0);
            declare_parameter<int64_t>("reconstructed_frames_png_compression", 3);
        }

        void validateInterfaceSelection() const
        {
            if (get_parameter("feature_provider").as_string() != "fibar_harris" ||
                get_parameter("patch_provider").as_string() != "fibar")
            {
                throw std::invalid_argument("ROS2 event-only mode requires fibar_harris and "
                                            "fibar providers");
            }
            if (get_parameter("superevent_enabled").as_bool())
            {
                throw std::invalid_argument("SuperEvent is a future-only provider");
            }
            const std::string bootstrap_mode = get_parameter("bootstrap_mode").as_string();
            if (bootstrap_mode != "events" && bootstrap_mode != "klt")
            {
                throw std::invalid_argument("bootstrap_mode must be events or klt");
            }
        }

        void configureDisplayOutputs()
        {
            display_features_ = get_parameter("display_features").as_bool();
            render_config_.scale = get_parameter("scale").as_double();
            render_config_.arrow_length =
                get_parameter("arrow_length").as_double();
            render_config_.draw_patch_outlines =
                get_parameter("display_feature_patches").as_bool();
            render_config_.draw_feature_ids =
                get_parameter("display_feature_id").as_bool();

            const double maximum_rate_hz =
                get_parameter("visualization_max_rate_hz").as_double();
            if (!std::isfinite(render_config_.scale) ||
                render_config_.scale <= 0.0 ||
                !std::isfinite(render_config_.arrow_length) ||
                render_config_.arrow_length < 0.0 ||
                !std::isfinite(maximum_rate_hz) || maximum_rate_hz <= 0.0)
            {
                throw std::invalid_argument(
                    "feature visualization parameters are invalid");
            }
            const double period_us = std::ceil(1000000.0 / maximum_rate_hz);
            if (!std::isfinite(period_us) ||
                period_us >
                    static_cast<double>(std::numeric_limits<int64_t>::max()))
            {
                throw std::invalid_argument(
                    "visualization_max_rate_hz produces an invalid period");
            }
            visualization_period_us_ =
                std::max<int64_t>(1, static_cast<int64_t>(period_us));

            SReconstructedFrameWriterConfig writer_config;
            writer_config.output_directory =
                get_parameter("reconstructed_frames_directory").as_string();
            writer_config.stride =
                ReadSizeParameter(*this, "reconstructed_frames_stride");
            writer_config.maximum_count =
                ReadSizeParameter(*this, "reconstructed_frames_max_count");
            writer_config.png_compression =
                ReadIntParameter(*this, "reconstructed_frames_png_compression");
            reconstructed_frame_writer_ =
                std::make_unique<CReconstructedFrameWriter>(writer_config);
        }

        eklt_core::SEkltTrackerConfig makeTrackerConfig(int width, int height) const
        {
            eklt_core::SEkltTrackerConfig config;
            config.width = width;
            config.height = height;
            config.initialization_mode = eklt_core::ETrackerInitializationMode::EventOnlyFibar;
            config.bootstrap_mode =
                get_parameter("bootstrap_mode").as_string() == "klt"
                    ? eklt_core::ETrackerBootstrapMode::Klt
                    : eklt_core::ETrackerBootstrapMode::Events;

            config.max_corners = ReadIntParameter(*this, "max_corners");
            config.min_corners = ReadIntParameter(*this, "min_corners");
            config.min_distance = get_parameter("min_distance").as_double();
            config.quality_level = get_parameter("quality_level").as_double();
            config.block_size = ReadIntParameter(*this, "block_size");
            config.harris_k = get_parameter("harris_k").as_double();

            config.patch_size = ReadIntParameter(*this, "patch_size");
            config.batch_size = ReadIntParameter(*this, "batch_size");
            config.update_every_n_events =
                ReadIntParameter(*this, "update_every_n_events");
            config.max_num_iterations = ReadIntParameter(*this, "max_num_iterations");
            config.tracking_quality = get_parameter("tracking_quality").as_double();
            config.displacement_px = get_parameter("displacement_px").as_double();
            config.log_eps = get_parameter("log_eps").as_double();
            config.first_image_t_us = get_parameter("first_image_t_us").as_int();

            config.reconstruction_interval_events =
                ReadIntParameter(*this, "event_only_reconstruction_interval_events");
            config.fibar_cutoff_time_us =
                ReadUint32Parameter(*this, "fibar_cutoff_time_us");
            config.fibar_fill_ratio = get_parameter("fibar_fill_ratio").as_double();
            config.fibar_use_spatial_filter =
                get_parameter("fibar_use_spatial_filter").as_bool();
            return config;
        }

        void openTracksFile(const std::string &path)
        {
            if (path.empty())
            {
                return;
            }

            // Create only the explicitly requested output parent so live camera
            // demos do not depend on pre-existing repository directories.
            const std::filesystem::path output_path(path);
            const std::filesystem::path parent = output_path.parent_path();
            if (!parent.empty())
            {
                std::error_code error;
                std::filesystem::create_directories(parent, error);
                if (error)
                {
                    throw std::runtime_error("failed to create track output directory: " +
                                             error.message());
                }
            }

            tracks_file_.open(output_path, std::ios::out | std::ios::trunc);
            if (!tracks_file_.is_open())
            {
                throw std::runtime_error("failed to open tracks_file_txt: " + path);
            }
            tracks_file_ << std::fixed << std::setprecision(9);
        }

        void openProcessingTimingFile(const std::string &path)
        {
            if (path.empty())
            {
                return;
            }

            // Keep timing output independent of track-file selection while
            // creating only the explicitly requested parent directory.
            const std::filesystem::path output_path(path);
            const std::filesystem::path parent = output_path.parent_path();
            if (!parent.empty())
            {
                std::error_code error;
                std::filesystem::create_directories(parent, error);
                if (error)
                {
                    throw std::runtime_error("failed to create processing timing directory: " +
                                             error.message());
                }
            }

            processing_timing_file_.open(output_path,
                                         std::ios::out | std::ios::trunc);
            if (!processing_timing_file_.is_open())
            {
                throw std::runtime_error("failed to open processing_timing_file_csv: " + path);
            }
            processing_timing_file_
                << "packet_index,event_time_s,fibar_ms,eklt_ms,overhead_ms,total_ms\n";
            processing_timing_file_.flush();
            if (!processing_timing_file_)
            {
                throw std::runtime_error("failed to initialize processing_timing_file_csv: " +
                                         path);
            }
        }

        void handlePacket(const event_camera_msgs::msg::EventPacket &packet)
        {
            using TClock = std::chrono::steady_clock;
            const TClock::time_point packet_start = TClock::now();
            ++received_packet_count_;
            recordSequence(packet.seq);

            try
            {
                // Decode and submit one complete packet synchronously so the
                // native all-or-nothing batch and ordering contracts are kept.
                std::vector<eklt_core::SEventSample> events = decoder_.decode(packet);
                decoded_event_count_ += static_cast<uint64_t>(events.size());
                if (events.empty())
                {
                    publishStatistics();
                    return;
                }

                ensureTracker(static_cast<int>(packet.width), static_cast<int>(packet.height));
                if (!tracker_->acceptEvents(std::move(events)))
                {
                    throw std::runtime_error("native event-only batch was not accepted");
                }

                ++accepted_packet_count_;
                publishTrackSamples();
                try
                {
                    publishSnapshotOutputs(packet.header);
                }
                catch (const std::exception &error)
                {
                    ++output_failure_count_;
                    RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                          "EKLT snapshot output failed: %s",
                                          error.what());
                }

                // Measure through every requested track, topic, and frame
                // output. Statistics and the timing CSV itself remain outside
                // the interval so diagnostics do not recursively time their
                // own serialization.
                try
                {
                    recordProcessingTiming(packet_start);
                }
                catch (const std::exception &error)
                {
                    ++output_failure_count_;
                    RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                          "EKLT processing timing output failed: %s",
                                          error.what());
                }
            }
            catch (const std::exception &error)
            {
                ++rejected_packet_count_;
                RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                      "EventPacket rejected: %s", error.what());
            }

            publishStatistics();
        }

        void recordProcessingTiming(const std::chrono::steady_clock::time_point &packet_start)
        {
            const eklt_core::STrackerTimingSample native_timing =
                tracker_->lastProcessingTiming();
            if (!native_timing.valid())
            {
                throw std::runtime_error("native tracker returned an invalid timing sample");
            }

            const std::chrono::steady_clock::time_point packet_finish =
                std::chrono::steady_clock::now();
            const std::chrono::duration<double, std::milli>
                measured_duration(packet_finish - packet_start);
            const double measured_total_ms = measured_duration.count();
            latest_fibar_ms_ = native_timing.fibar_ms;
            latest_eklt_ms_ = native_timing.eklt_ms;
            latest_total_ms_ =
                std::max(measured_total_ms, native_timing.native_total_ms);
            latest_overhead_ms_ =
                latest_total_ms_ - native_timing.native_total_ms;

            if (!processing_timing_file_.is_open())
            {
                return;
            }

            // Persist one bounded row per accepted non-empty EventPacket. The
            // additive columns reconstruct total_ms without retaining history
            // in the ROS2 node.
            processing_timing_file_
                << accepted_packet_count_ << ","
                << std::fixed << std::setprecision(9)
                << static_cast<double>(native_timing.t_us) / 1000000.0 << ","
                << latest_fibar_ms_ << ","
                << latest_eklt_ms_ << ","
                << latest_overhead_ms_ << ","
                << latest_total_ms_ << "\n";
            processing_timing_file_.flush();
            if (!processing_timing_file_)
            {
                throw std::runtime_error("failed to append processing timing row");
            }
            ++processing_timing_row_count_;
        }

        void recordSequence(uint64_t sequence)
        {
            if (has_previous_sequence_)
            {
                const uint64_t expected = previous_sequence_ + 1U;
                if (sequence != expected)
                {
                    ++sequence_discontinuity_count_;
                    RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                                         "EventPacket sequence discontinuity: expected %llu, "
                                         "received %llu",
                                         static_cast<unsigned long long>(expected),
                                         static_cast<unsigned long long>(sequence));
                }
            }
            previous_sequence_ = sequence;
            has_previous_sequence_ = true;
        }

        void ensureTracker(int width, int height)
        {
            if (!tracker_)
            {
                const eklt_core::SEkltTrackerConfig config =
                    makeTrackerConfig(width, height);
                tracker_ =
                    std::make_unique<eklt_core::CEkltTrackerOrchestrator>(config);
                RCLCPP_INFO(get_logger(), "Initialized native event-only EKLT for %dx%d",
                            width, height);
                return;
            }
            if (tracker_->config().width != width || tracker_->config().height != height)
            {
                throw std::invalid_argument("EventPacket geometry changed during tracking");
            }
        }

        void publishTrackSamples()
        {
            const std::vector<eklt_core::STrackSample> samples =
                tracker_->takeTrackSamples();

            // Avoid constructing one ROS message per sample when only the
            // optional track file is being used.
            const bool publish_topic = tracks_publisher_->get_subscription_count() > 0U;
            for (const eklt_core::STrackSample &sample : samples)
            {
                const std::string row = MakeTrackRow(sample);
                if (tracks_file_.is_open())
                {
                    tracks_file_ << row << "\n";
                }

                if (publish_topic)
                {
                    std_msgs::msg::String message;
                    message.data = row;
                    tracks_publisher_->publish(message);
                }
            }
            if (tracks_file_.is_open() && !samples.empty())
            {
                tracks_file_.flush();
            }
        }

        void publishSnapshotOutputs(const std_msgs::msg::Header &packet_header)
        {
            const bool publish_init_image =
                init_debug_publisher_->get_subscription_count() > 0U;
            const bool publish_feature_image =
                display_features_ &&
                feature_tracks_publisher_->get_subscription_count() > 0U;
            const bool write_reconstructed_frame =
                reconstructed_frame_writer_->enabled();
            if (!publish_init_image && !publish_feature_image &&
                !write_reconstructed_frame)
            {
                return;
            }

            const eklt_core::STrackerSnapshot snapshot = tracker_->snapshot();
            if (!snapshot.valid())
            {
                return;
            }

            // Normalize each newly reconstructed image at most once, then
            // share the same display bytes between topic and PNG outputs.
            if ((publish_init_image || write_reconstructed_frame) &&
                snapshot.image.t_us != last_reconstructed_image_t_us_)
            {
                if (last_reconstructed_image_t_us_ >= 0 &&
                    snapshot.image.t_us < last_reconstructed_image_t_us_)
                {
                    throw std::runtime_error(
                        "native reconstruction timestamp regressed");
                }

                std::vector<uint8_t> pixels =
                    MakeMono8Image(snapshot.image.image);
                const std::size_t expected_size =
                    static_cast<std::size_t>(snapshot.image.width) *
                    static_cast<std::size_t>(snapshot.image.height);
                if (pixels.size() != expected_size)
                {
                    throw std::runtime_error(
                        "native snapshot cannot be converted to mono8");
                }

                if (write_reconstructed_frame)
                {
                    reconstructed_frame_writer_->write(pixels, snapshot.image.width,
                                                       snapshot.image.height,
                                                       snapshot.image.t_us);
                }
                if (publish_init_image)
                {
                    sensor_msgs::msg::Image message;
                    message.header =
                        MakeImageHeader(packet_header, snapshot.image.t_us);
                    message.height =
                        static_cast<uint32_t>(snapshot.image.height);
                    message.width =
                        static_cast<uint32_t>(snapshot.image.width);
                    message.encoding = "mono8";
                    message.is_bigendian = false;
                    message.step =
                        static_cast<sensor_msgs::msg::Image::_step_type>(
                            snapshot.image.width);
                    message.data = std::move(pixels);
                    init_debug_publisher_->publish(message);
                }
                last_reconstructed_image_t_us_ = snapshot.image.t_us;
            }

            if (!publish_feature_image ||
                snapshot.t_us == last_feature_image_t_us_)
            {
                return;
            }
            if (last_feature_image_t_us_ >= 0)
            {
                if (snapshot.t_us < last_feature_image_t_us_)
                {
                    throw std::runtime_error(
                        "native feature snapshot timestamp regressed");
                }
                if (snapshot.t_us - last_feature_image_t_us_ <
                    visualization_period_us_)
                {
                    return;
                }
            }
            if (visualization_origin_t_us_ < 0)
            {
                visualization_origin_t_us_ = snapshot.image.t_us;
            }

            // The shared renderer owns annotation policy; this boundary only
            // maps its contiguous BGR bytes into a depth-one ROS2 topic.
            eklt_visualization::SRenderedTrackImage rendered =
                eklt_visualization::RenderFeatureTrackOverlay(snapshot,
                                                              render_config_,
                                                              visualization_origin_t_us_);
            if (!rendered.valid())
            {
                throw std::runtime_error(
                    "native feature renderer returned invalid storage");
            }

            sensor_msgs::msg::Image feature_message;
            feature_message.header =
                MakeImageHeader(packet_header, rendered.t_us);
            feature_message.height = static_cast<uint32_t>(rendered.height);
            feature_message.width = static_cast<uint32_t>(rendered.width);
            feature_message.encoding = "bgr8";
            feature_message.is_bigendian = false;
            feature_message.step =
                static_cast<sensor_msgs::msg::Image::_step_type>(rendered.step);
            feature_message.data = std::move(rendered.pixels);
            feature_tracks_publisher_->publish(feature_message);
            last_feature_image_t_us_ = snapshot.t_us;
        }

        void publishStatistics()
        {
            // JSON formatting is diagnostic-only and can be skipped when the
            // topic is not observed.
            if (stats_publisher_->get_subscription_count() == 0U)
            {
                return;
            }

            eklt_core::STrackerStatistics native_statistics;
            std::size_t gradient_cache_count = 0U;
            if (tracker_)
            {
                native_statistics = tracker_->statistics();
                gradient_cache_count = tracker_->gradientCacheCount();
            }

            std::ostringstream payload;
            payload << "{\"received_packets\":" << received_packet_count_
                    << ",\"accepted_packets\":" << accepted_packet_count_
                    << ",\"rejected_packets\":" << rejected_packet_count_
                    << ",\"output_failures\":" << output_failure_count_
                    << ",\"sequence_discontinuities\":" << sequence_discontinuity_count_
                    << ",\"decoded_events\":" << decoded_event_count_
                    << ",\"accepted_events\":" << native_statistics.accepted_events
                    << ",\"processed_events\":" << native_statistics.processed_events
                    << ",\"tracks\":" << native_statistics.active_tracks
                    << ",\"optimization_updates\":"
                    << native_statistics.optimization_updates
                    << ",\"initializations\":" << native_statistics.initialization_count
                    << ",\"last_initialized\":"
                    << native_statistics.last_initialized_count
                    << ",\"lost\":" << native_statistics.lost_count
                    << ",\"gradient_caches\":" << gradient_cache_count
                    << ",\"saved_reconstructed_frames\":"
                    << reconstructed_frame_writer_->savedCount()
                    << ",\"processing_timing_rows\":"
                    << processing_timing_row_count_
                    << ",\"latest_fibar_ms\":" << latest_fibar_ms_
                    << ",\"latest_eklt_ms\":" << latest_eklt_ms_
                    << ",\"latest_overhead_ms\":" << latest_overhead_ms_
                    << ",\"latest_total_ms\":" << latest_total_ms_ << "}";

            std_msgs::msg::String message;
            message.data = payload.str();
            stats_publisher_->publish(message);
        }

        CEventPacketDecoder decoder_;
        std::unique_ptr<eklt_core::CEkltTrackerOrchestrator> tracker_;
        std::unique_ptr<CReconstructedFrameWriter> reconstructed_frame_writer_;
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr tracks_publisher_;
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr stats_publisher_;
        rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr init_debug_publisher_;
        rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr
            feature_tracks_publisher_;
        rclcpp::Subscription<event_camera_msgs::msg::EventPacket>::SharedPtr
            event_subscription_;
        std::ofstream tracks_file_;
        std::ofstream processing_timing_file_;
        uint64_t received_packet_count_{0};
        uint64_t accepted_packet_count_{0};
        uint64_t rejected_packet_count_{0};
        uint64_t output_failure_count_{0};
        uint64_t sequence_discontinuity_count_{0};
        uint64_t decoded_event_count_{0};
        uint64_t previous_sequence_{0};
        uint64_t processing_timing_row_count_{0};
        eklt_visualization::SFeatureTrackRenderConfig render_config_;
        double latest_fibar_ms_{0.0};
        double latest_eklt_ms_{0.0};
        double latest_overhead_ms_{0.0};
        double latest_total_ms_{0.0};
        int64_t visualization_period_us_{1};
        int64_t visualization_origin_t_us_{-1};
        int64_t last_reconstructed_image_t_us_{-1};
        int64_t last_feature_image_t_us_{-1};
        bool display_features_{true};
        bool has_previous_sequence_{false};
    };

} // namespace eklt_rebuild

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    try
    {
        rclcpp::spin(std::make_shared<eklt_rebuild::CEventOnlyEkltNode>());
    }
    catch (const std::exception &error)
    {
        RCLCPP_FATAL(rclcpp::get_logger("eklt_rebuild_event_only"), "%s", error.what());
        rclcpp::shutdown();
        return 1;
    }
    rclcpp::shutdown();
    return 0;
}
