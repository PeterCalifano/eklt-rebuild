#pragma once

#include <dvs_msgs/EventArray.h>
#include <gflags/gflags.h>
#include <image_transport/image_transport.h>
#include <ros/ros.h>
#include <sensor_msgs/Image.h>

#include <deque>
#include <fstream>
#include <mutex>

#include "optimizer.h"
#include "patch.h"
#include "tracker_utils.h"
#include "viewer.h"

DECLARE_double(tracking_quality);

namespace tracker
{
    /**
     * @brief ROS1 EKLT tracker frontend.
     *
     * The tracker initializes features from grayscale frames, assigns incoming
     * events to feature patches, and optimizes each patch against the reference
     * image gradient. Frames provide corner extraction and bootstrap data; events
     * drive asynchronous feature updates between frames.
     */
    class Tracker
    {
      public:
        /**
         * @brief Construct subscribers, tracker state, and optional track export.
         * @param nh ROS node handle used for subscriptions and parameters.
         * @param viewer Viewer receiving feature-track snapshots.
         */
        Tracker(ros::NodeHandle &nh, viewer::Viewer &viewer);

      private:
        /**
         * @brief Initialize optimizer, viewer, and feature patches from one image.
         * @param image_it Iterator to a CV_8U grayscale reference image.
         */
        void init(const ImageBuffer::iterator &image_it);

        /**
         * @brief Worker loop that consumes buffered events and updates patches.
         */
        void processEvents();

        /**
         * @brief Block until an event is available in the event buffer.
         * @param ev Output event popped from the front of the buffer.
         */
        inline void waitForEvent(dvs_msgs::Event &ev)
        {
            // Define ros::Rate timer (helper class for running loops at desired frequency)
            static ros::Rate rate_controller(100); // 100 Hz

            // Processing loop
            while (true)
            {
                {
                    std::unique_lock<std::mutex> lock(events_mutex_);
                    if (events_.size() > 0)
                    {
                        ev = events_.front();
                        events_.pop_front();
                        return;
                    }
                }
                rate_controller.sleep();
                // TODO improve application logging
                VLOG_EVERY_N(1, 30) << "Waiting for events...";
            }
        }

        /**
         * @brief Block until the first image arrives.
         * @param current_image_it Output iterator to the first buffered image.
         */
        void waitForFirstImage(ImageBuffer::iterator &current_image_it);

        /**
         * @brief Advance image iterator to the newest frame before an event time.
         * @param t_start Target event timestamp.
         * @param current_image_it Iterator updated in-place when a newer valid image exists.
         * @return True when the iterator advanced.
         */
        inline bool updateFirstImageBeforeTime(ros::Time t_start, ImageBuffer::iterator &current_image_it)
        {
            return AdvanceToFirstImageBeforeTimestamp(images_, t_start, current_image_it);
        }

        /**
         * @brief Try to bootstrap every uninitialized patch with available image/event data.
         * @param patches Patches to inspect and update.
         * @param image_it Iterator to the current image used for bootstrapping.
         */
        void bootstrapAllPossiblePatches(Patches &patches,
                                         const ImageBuffer::iterator &image_it);

        /**
         * @brief Bootstrap one patch using KLT over two frames.
         * @param patch Patch to initialize.
         * @param last_image Previous grayscale image.
         * @param current_image Current grayscale image.
         */
        void bootstrapFeatureKLT(Patch &patch,
                                 const cv::Mat &last_image,
                                 const cv::Mat &current_image);

        /**
         * @brief Bootstrap one patch from an event frame with zero initial translation.
         * @param patch Patch to initialize.
         * @param event_frame Patch event frame produced from recent events.
         */
        void bootstrapFeatureEvents(Patch &patch, const cv::Mat &event_frame);

        /**
         * @brief Replace lost patches with newly detected corners.
         * @param lost_indices Indices of patch slots that need replacement.
         * @param image_it Image used for feature detection.
         */
        void addFeatures(std::vector<int> &lost_indices,
                         const ImageBuffer::iterator &image_it);

        /**
         * @brief Insert one event into a patch and run an update when enough events accumulated.
         * @param patch Patch receiving the event.
         * @param event Event assigned to the patch.
         */
        void updatePatch(Patch &patch, const dvs_msgs::Event &event);

        /**
         * @brief Reset lost patch slots from candidate replacement patches.
         * @param new_patches Candidate patches generated from current corners.
         * @param lost_indices Patch slot indices to replace.
         * @param image_it Reference image for the reset patches.
         */
        void resetPatches(Patches &new_patches,
                          std::vector<int> &lost_indices,
                          const ImageBuffer::iterator &image_it);

        /**
         * @brief Initialize patch slots from corners detected in one image.
         * @param patches Output patch collection.
         * @param lost_indices Output lost-slot indices available for replacement.
         * @param corners Maximum number of corners to initialize.
         * @param image_it Reference image iterator.
         */
        void initPatches(Patches &patches,
                         std::vector<int> &lost_indices,
                         const int &corners,
                         const ImageBuffer::iterator &image_it);

        /**
         * @brief Detect and extract feature patches from one image.
         * @param patches Output patch collection.
         * @param num_patches Maximum number of patches to extract.
         * @param image_it Reference image iterator.
         */
        void extractPatches(Patches &patches,
                            const int &num_patches,
                            const ImageBuffer::iterator &image_it);

        /**
         * @brief Add constant-value borders around an image.
         * @param in Input image.
         * @param out Output padded image.
         * @param p Border width in pixels.
         */
        inline void padBorders(const cv::Mat &in, cv::Mat &out, int p)
        {
            out = cv::Mat(in.rows + p * 2, in.cols + p * 2, in.depth());
            cv::Mat gray(out, cv::Rect(p, p, in.cols, in.rows));
            copyMakeBorder(in, out, p, p, p, p, cv::BORDER_CONSTANT);
        }

        /**
         * @brief Decide whether a patch should be discarded.
         * @param patch Patch to inspect.
         * @return True when the patch leaves the image bounds or falls below tracking quality.
         */
        inline bool shouldDiscard(Patch &patch)
        {
            bool out_of_fov = (patch.center_.y < 0 || patch.center_.y >= sensor_size_.height || patch.center_.x < 0 || patch.center_.x >= sensor_size_.width);
            bool exceeded_error = patch.tracking_quality_ < FLAGS_tracking_quality;

            return exceeded_error || out_of_fov;
        }

        /**
         * @brief Set adaptive event batch size according to equation (15) in the EKLT paper.
         * @param patch Patch whose batch size is updated.
         * @param I_x Horizontal image gradient.
         * @param I_y Vertical image gradient.
         * @param d Displacement scaling parameter.
         */
        void setBatchSize(Patch &patch,
                          const cv::Mat &I_x,
                          const cv::Mat &I_y,
                          const double &d);

        /**
         * @brief ROS callback for incoming event arrays.
         * @param msg Event-array message from the configured event topic.
         */
        void eventsCallback(const dvs_msgs::EventArray::ConstPtr &msg);

        /**
         * @brief ROS callback for incoming grayscale images.
         * @param msg Image message from the configured image topic.
         */
        void imageCallback(const sensor_msgs::Image::ConstPtr &msg);

        /**
         * @brief Insert one event into the shared buffer while preserving timestamp order.
         * @param e Event to insert.
         */
        inline void insertEventInSortedBuffer(const dvs_msgs::Event &e)
        {
            std::unique_lock<std::mutex> lock(events_mutex_);
            InsertEventInSortedOrder(events_, e);
        }

        /**
         * @brief Sensor resolution inferred from the first image or event message.
         */
        cv::Size sensor_size_;

        /**
         * @brief True after the first image has been received and buffered.
         */
        bool got_first_image_;

        /**
         * @brief Iterator to the image currently used for event processing.
         */
        ImageBuffer::iterator current_image_it_;

        /**
         * @brief Most recent event or image timestamp observed by the tracker.
         */
        ros::Time most_current_time_;

        /**
         * @brief Event queue protected by @ref events_mutex_.
         */
        EventBuffer events_;

        /**
         * @brief Image buffer protected by @ref images_mutex_.
         */
        ImageBuffer images_;

        /**
         * @brief ROS event subscriber.
         */
        ros::Subscriber event_sub_;

        /**
         * @brief ROS image subscriber.
         */
        image_transport::Subscriber image_sub_;

        /**
         * @brief Image transport handle used by the image subscriber.
         */
        image_transport::ImageTransport it_;

        /**
         * @brief Node handle owned by the tracker.
         */
        ros::NodeHandle nh_;

        /**
         * @brief Current patch slots tracked by EKLT.
         */
        Patches patches_;

        /**
         * @brief Cached per-patch image gradients keyed by patch id.
         */
        std::map<int, std::pair<cv::Mat, cv::Mat>> patch_gradients_;

        /**
         * @brief Patch indices available for replacement.
         */
        std::vector<int> lost_indices_;

        /**
         * @brief Viewer receiving copies of current feature state.
         */
        viewer::Viewer *viewer_ptr_ = NULL;

        /**
         * @brief Nonlinear optimizer used for patch updates.
         */
        nlls::Optimizer optimizer_;

        /**
         * @brief Mutex protecting @ref events_.
         */
        std::mutex events_mutex_;

        /**
         * @brief Mutex protecting @ref images_.
         */
        std::mutex images_mutex_;

        /**
         * @brief Optional text output stream for feature tracks.
         */
        std::ofstream tracks_file_;
    };

} // namespace tracker
