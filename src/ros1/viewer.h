/// @file viewer.h
/// @brief Declares the asynchronous ROS1 feature-track viewer.
/// @details The viewer consumes snapshots of native-backed patch state and
///          publishes a `bgr8` overlay without owning tracker computation.

#pragma once

#include <atomic>
#include <mutex>
#include <string>
#include <thread>

#include <image_transport/image_transport.h>
#include <opencv2/core.hpp>
#include <ros/ros.h>

#include "types.h"

namespace viewer
{

    /// @brief Publishes annotated EKLT feature-track images through ROS1.
    class Viewer
    {
      public:
        /// @brief Construct an empty viewer.
        /// @param nh ROS node handle used for image publication.
        explicit Viewer(ros::NodeHandle &nh);

        /// @brief Stop and join the publishing worker.
        ~Viewer();

        /// @brief Run the publishing loop until ROS or this viewer stops.
        void displayTracks();

        /// @brief Initialize viewer timing and publication state.
        /// @param timestamp First tracker image timestamp.
        void initViewData(const ros::Time &timestamp);

        /// @brief Copy current tracker state into the viewer buffer.
        /// @param snapshot Owning native image and feature state.
        /// @param timestamp Timestamp associated with the patch states.
        void setViewData(const eklt_core::STrackerSnapshot &snapshot,
                         const ros::Time &timestamp);

      private:
        /// @brief Draw feature annotations on an image.
        /// @param data Feature state snapshot to render.
        /// @param view Output annotated image.
        /// @param image Source image used as drawing background.
        void drawOnImage(const FeatureTrackData &data,
                         cv::Mat &view,
                         const cv::Mat &image);

        /// @brief Publish an OpenCV image as a ROS image message.
        /// @param image Image to publish.
        /// @param stamp Timestamp assigned to the ROS message header.
        /// @param encoding ROS image encoding string.
        /// @param publisher Image transport publisher.
        void publishImage(const cv::Mat &image,
                          const ros::Time &stamp,
                          const std::string &encoding,
                          const image_transport::Publisher &publisher);

        /// @brief Node handle retained for ROS resource lifetime.
        ros::NodeHandle nh_;

        /// @brief Latest tracker snapshot copied into the viewer.
        FeatureTrackData feature_track_data_;

        /// @brief Last rendered feature-track preview image.
        cv::Mat feature_track_view_;

        /// @brief Publisher for annotated feature-track images.
        image_transport::Publisher tracks_pub_;

        /// @brief Image transport handle used by `tracks_pub_`.
        image_transport::ImageTransport it_;

        /// @brief Mutex protecting `feature_track_data_`.
        std::mutex data_mutex_;

        /// @brief Worker thread that publishes feature-track previews.
        std::thread display_thread_;

        /// @brief Set during teardown to stop the display worker.
        std::atomic<bool> stop_requested_;

        /// @brief True after initial timing and image data are available.
        std::atomic<bool> got_first_image_;
    };

} // namespace viewer
