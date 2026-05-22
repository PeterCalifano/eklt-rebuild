#pragma once

#include <mutex>

#include <image_transport/image_transport.h>
#include <opencv2/core/core.hpp>
#include <opencv2/imgproc/imgproc_c.h>
#include <ros/ros.h>

#include "patch.h"
#include "types.h"

namespace viewer
{
    /**
     * @brief ROS image viewer for EKLT feature-track overlays.
     *
     * The viewer receives snapshots from the tracker, draws feature positions,
     * optional IDs and patch boxes, then publishes the annotated image through
     * image_transport.
     */
    class Viewer
    {
      public:
        /**
         * @brief Construct publishers and initialize empty viewer state.
         * @param nh ROS node handle used for image publication.
         */
        Viewer(ros::NodeHandle &nh);

        /**
         * @brief Destroy viewer resources.
         */
        ~Viewer();

        /**
         * @brief Main publishing loop for feature-track visualization.
         */
        void displayTracks();

        /**
         * @brief Initialize viewer timing state before the first track snapshot.
         * @param t Timestamp of the first image or tracker initialization.
         */
        void initViewData(ros::Time t);

        /**
         * @brief Copy current tracker state into the viewer buffer.
         * @param patches Current tracker patches.
         * @param t Timestamp associated with the patch states.
         * @param image_it Image used as visualization background.
         */
        void setViewData(tracker::Patches &patches, ros::Time &t,
                         tracker::ImageBuffer::iterator image_it);

      private:
        /**
         * @brief Draw feature annotations on an image.
         * @param data Feature state snapshot to render.
         * @param view Output annotated image.
         * @param image Source image used as drawing background.
         */
        void drawOnImage(FeatureTrackData &data, cv::Mat &view, cv::Mat &image);

        /**
         * @brief Publish an OpenCV image as a ROS image message.
         * @param image Image to publish.
         * @param stamp Timestamp assigned to the ROS message header.
         * @param encoding ROS image encoding string.
         * @param pub Image transport publisher.
         */
        void publishImage(cv::Mat image, ros::Time stamp, std::string encoding, image_transport::Publisher pub);

        /**
         * @brief Node handle owned by the viewer.
         */
        ros::NodeHandle nh_;

        /**
         * @brief Latest tracker snapshot copied into the viewer.
         */
        FeatureTrackData feature_track_data_;

        /**
         * @brief Last rendered feature-track preview image.
         */
        cv::Mat feature_track_view_;

        /**
         * @brief Publisher for annotated feature-track images.
         */
        image_transport::Publisher tracks_pub_;

        /**
         * @brief Image transport handle used by @ref tracks_pub_.
         */
        image_transport::ImageTransport it_;

        /**
         * @brief Mutex protecting @ref feature_track_data_.
         */
        std::mutex data_mutex_;

        /**
         * @brief True after the viewer has received initial timing/image data.
         */
        bool got_first_image_;
    };

} // namespace viewer
