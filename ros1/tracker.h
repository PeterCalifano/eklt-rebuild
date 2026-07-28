/// @file tracker.h
/// @brief Declares the thin ROS1 overlay for the native EKLT orchestrator.
/// @details ROS1 owns message conversion, bounded callback buffering, track
///          serialization, and viewer publication. Reconstruction, image
///          scheduling, initialization, KLT, Ceres updates, and feature
///          lifecycle remain in the ROS-free C++ library.

#pragma once

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <fstream>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

#include <dvs_msgs/EventArray.h>
#include <image_transport/image_transport.h>
#include <ros/ros.h>
#include <sensor_msgs/Image.h>

#include "eklt_core/tracker_orchestrator.h"
#include "viewer.h"

namespace tracker
{

    /// @brief Converts ROS1 transport data around one native EKLT state machine.
    class Tracker
    {
      public:
        /// @brief Construct subscriptions and the bounded native-input worker.
        /// @param nh ROS node handle used for subscriptions.
        /// @param viewer Existing ROS image publisher for native snapshots.
        /// @throws std::invalid_argument If a ROS flag violates the native
        ///         tracker or viewer contract.
        Tracker(ros::NodeHandle &nh, viewer::Viewer &viewer);

        /// @brief Stop the input worker and release ROS resources.
        ~Tracker();

      private:
        /// @brief Distinguishes frame and event work items in callback order.
        enum class EInputKind
        {
            Frame,
            Events
        };

        /// @brief One owning transport batch awaiting native processing.
        struct SQueuedInput
        {
            EInputKind kind{EInputKind::Events};
            int width{0};
            int height{0};
            eklt_core::SImageFrame frame;
            std::vector<eklt_core::SEventSample> events;
        };

        /// @brief Validate flags that do not depend on sensor geometry.
        void validateFlags() const;

        /// @brief Build the complete native configuration for fixed geometry.
        /// @param width Sensor width in pixels.
        /// @param height Sensor height in pixels.
        /// @return Native configuration populated from ROS1 gflags.
        eklt_core::SEkltTrackerConfig makeConfig(int width, int height) const;

        /// @brief Add one input while applying bounded callback backpressure.
        /// @param input Owning input batch.
        void queueInput(SQueuedInput input);

        /// @brief Consume queued transport batches until shutdown.
        void processInputs();

        /// @brief Process one batch through the synchronous native API.
        /// @param input Owning frame or event batch in callback order.
        void processInput(SQueuedInput input);

        /// @brief Create or validate the native tracker for one sensor.
        /// @param width Input sensor width.
        /// @param height Input sensor height.
        /// @return True when a matching native tracker is available.
        bool ensureOrchestrator(int width, int height);

        /// @brief Write emitted native track samples to the configured file.
        /// @param samples Deterministically ordered native track rows.
        void writeTracks(const std::vector<eklt_core::STrackSample> &samples);

        /// @brief Publish a coherent native state snapshot when due.
        /// @param force True for the first initialized state.
        void publishSnapshot(bool force);

        /// @brief Receive and convert one ROS1 event array.
        /// @param msg Event array from the configured topic.
        void eventsCallback(const dvs_msgs::EventArray::ConstPtr &msg);

        /// @brief Receive and convert one frame-backed grayscale image.
        /// @param msg Image from the configured topic.
        void imageCallback(const sensor_msgs::Image::ConstPtr &msg);

        /// @brief Maximum work items retained in addition to the active batch.
        static constexpr std::size_t kMaxQueuedInputs = 2;

        /// @brief Node handle retained for ROS resource lifetime.
        ros::NodeHandle nh_;

        /// @brief Image transport handle for the optional frame subscription.
        image_transport::ImageTransport image_transport_;

        /// @brief ROS event subscriber.
        ros::Subscriber event_sub_;

        /// @brief Optional frame-image subscriber.
        image_transport::Subscriber image_sub_;

        /// @brief Existing ROS image publisher receiving native snapshots.
        viewer::Viewer *viewer_ptr_{nullptr};

        /// @brief Complete ROS-free tracking state, created after geometry arrives.
        std::unique_ptr<eklt_core::CEkltTrackerOrchestrator> orchestrator_;

        /// @brief Callback-ordered frame and event inputs.
        std::deque<SQueuedInput> inputs_;

        /// @brief Mutex protecting the bounded input queue.
        std::mutex inputs_mutex_;

        /// @brief Signals input arrival, queue capacity, and shutdown.
        std::condition_variable inputs_condition_;

        /// @brief Worker that exclusively calls the native orchestrator.
        std::thread input_processing_thread_;

        /// @brief Optional text output stream for feature tracks.
        std::ofstream tracks_file_;

        /// @brief Set after frame-backed initialization accepts its first image.
        std::atomic<bool> ready_for_frame_events_{false};

        /// @brief Set during teardown to stop callbacks and the worker.
        std::atomic<bool> stop_requested_{false};

        /// @brief True after the existing viewer starts its publishing worker.
        bool viewer_initialized_{false};

        /// @brief Accepted native events since the last viewer snapshot.
        std::size_t events_since_view_{0};
    };

} // namespace tracker
