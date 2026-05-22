#pragma once

#include <deque>
#include <mutex>
#include <random>

#include <dvs_msgs/Event.h>
#include <gflags/gflags.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#include "error.h"
#include "types.h"

DECLARE_int32(patch_size);
DECLARE_int32(batch_size);
DECLARE_int32(update_every_n_events);

namespace tracker
{

    /**
     * @brief Feature-centered EKLT patch with its local event buffer and warp state.
     *
     * A patch is initialized around a corner in a reference frame. Incoming events
     * that fall inside the current patch window are accumulated into an event frame,
     * then optimized against the cached image gradient to update warp and flow.
     */
    struct Patch
    {
        /**
         * @brief Construct a live patch around an initial feature position.
         * @param center Initial corner position in image coordinates.
         * @param t_init Timestamp of the image where the corner was extracted.
         */
        Patch(cv::Point2d center, ros::Time t_init) : init_center_(center), flow_angle_(0), t_init_(t_init), t_curr_(t_init), event_counter_(0), color_(0, 0, 255),
                                                      lost_(false), initialized_(false), tracking_quality_(1)
        {
            warping_ = cv::Mat::eye(3, 3, CV_64F);

            half_size_ = (FLAGS_patch_size - 1) / 2;
            batch_size_ = FLAGS_batch_size;
            update_rate_ = FLAGS_update_every_n_events;

            reset(init_center_, t_init);
        }

        /**
         * @brief Construct a sentinel lost patch.
         */
        Patch() : Patch(cv::Point2f(-1, -1), ros::Time::now())
        {
            // Constructor for initializing lost features.
            lost_ = true;
        }

        /**
         * @brief Check whether a pixel lies inside the current square patch window.
         * @param x Pixel x coordinate.
         * @param y Pixel y coordinate.
         * @return True when the pixel is within @ref half_size_ of @ref center_.
         */
        inline bool contains(double x, double y)
        {
            return half_size_ >= std::abs(x - center_.x) && half_size_ >= std::abs(y - center_.y);
        }

        /**
         * @brief Add one event to the patch event buffer.
         * @param event Event already known to be relevant for this patch.
         *
         * Newest events are kept at the front. The buffer is clipped to the global
         * batch-size flag so each optimization step uses a bounded event window.
         */
        inline void insert(const dvs_msgs::Event &event)
        {
            event_buffer_.push_front(event);

            if (event_buffer_.size() > FLAGS_batch_size)
            {
                event_buffer_.pop_back();
            }

            event_counter_++;
        }

        /**
         * @brief Apply the inverse patch warp to a point.
         * @param unwarped Point in the current patch coordinate frame.
         * @param warped Output point in the reference patch coordinate frame.
         */
        inline void warpPixel(cv::Point2d unwarped, cv::Point2d &warped)
        {
            // compute the position of the feature according to the warp (equation (8) in the paper)
            cv::Mat W = warping_.inv();

            warped.x = W.at<double>(0, 0) * unwarped.x + W.at<double>(0, 1) * unwarped.y + W.at<double>(0, 2);
            warped.y = W.at<double>(1, 0) * unwarped.x + W.at<double>(1, 1) * unwarped.y + W.at<double>(1, 2);
        }

        /**
         * @brief Build the normalized event frame used by the optimizer and reset the event counter.
         * @param event_frame Output patch-sized image containing bilinear event accumulation.
         *
         * This implements the event image from equation (2) in the EKLT paper. The
         * patch timestamp is set to the midpoint of the event batch.
         */
        inline void getEventFramesAndReset(cv::Mat &event_frame)
        {
            // implements the function (2) in the paper
            event_frame = cv::Mat::zeros(2 * half_size_ + 1, 2 * half_size_ + 1, CV_64F);

            int iterations = batch_size_ < event_buffer_.size() ? batch_size_ - 1 : event_buffer_.size() - 1;
            for (int i = 0; i < iterations; i++)
            {
                dvs_msgs::Event &e = event_buffer_[i];

                if (!contains(e.x, e.y))
                    continue;

                int x = e.x - center_.x + half_size_;
                int y = e.y - center_.y + half_size_;
                double rx = e.x - center_.x + half_size_ - x;
                double ry = e.y - center_.y + half_size_ - y;

                int increment = e.polarity ? 1 : -1;

                event_frame.at<double>(y + 1, x + 1) += increment * rx * ry;
                event_frame.at<double>(y, x + 1) += increment * rx * (1 - ry);
                event_frame.at<double>(y + 1, x) += increment * (1 - rx) * ry;
                event_frame.at<double>(y, x) += increment * (1 - rx) * (1 - ry);
            }

            // Timestamp the event frame at the middle of the event batch.
            t_curr_ = ros::Time(0.5 * (event_buffer_[0].ts.toSec() + event_buffer_[iterations].ts.toSec()));
            event_counter_ = 0;
        }

        /**
         * @brief Reinitialize patch state after construction or track loss.
         * @param init_center New feature center in image coordinates.
         * @param t Timestamp of the reference image for the reset feature.
         */
        inline void reset(cv::Point2d init_center, ros::Time t)
        {
            // reset feature after it has been lost
            event_counter_ = 0;
            tracking_quality_ = 1;
            lost_ = false;
            initialized_ = false;
            flow_angle_ = 0;

            center_ = init_center;
            init_center_ = init_center;
            t_curr_ = t;
            t_init_ = t;

            warping_ = cv::Mat::eye(3, 3, CV_64F);
            event_buffer_.clear();

            // set random color
            static std::uniform_real_distribution<double> unif(0, 255);
            static std::default_random_engine re;
            color_ = cv::Scalar(unif(re), unif(re), unif(re));

            static int id = 0;
            id_ = id++;
        }

        /**
         * @brief Feature center in the reference image.
         */
        cv::Point2d init_center_;

        /**
         * @brief Current feature center after warp updates.
         */
        cv::Point2d center_;

        /**
         * @brief Homogeneous transform from reference patch to current patch.
         */
        cv::Mat warping_;

        /**
         * @brief Optical-flow direction angle in radians.
         */
        double flow_angle_;

        /**
         * @brief Half of the square patch side length in pixels.
         */
        int half_size_;

        /**
         * @brief Number of events accumulated since the last optimizer update.
         */
        int event_counter_;

        /**
         * @brief Timestamp of the reference frame where this feature was initialized.
         */
        ros::Time t_init_;

        /**
         * @brief Timestamp associated with the current event batch.
         */
        ros::Time t_curr_;

        /**
         * @brief Rescaled tracking quality used for outlier rejection.
         */
        double tracking_quality_;

        /**
         * @brief Display color used by the viewer.
         */
        cv::Scalar color_;

        /**
         * @brief Unique patch identifier used in visualization and track export.
         */
        int id_;

        /**
         * @brief Event batch size cached from runtime flags.
         */
        int batch_size_;

        /**
         * @brief Number of patch events between viewer updates.
         */
        int update_rate_;

        /**
         * @brief True when this slot is not currently tracking a valid feature.
         */
        bool lost_;

        /**
         * @brief True after initial flow has been bootstrapped.
         */
        bool initialized_;

        /**
         * @brief Most recent events assigned to this patch, newest first.
         */
        std::deque<dvs_msgs::Event> event_buffer_;
    };

} // namespace tracker
