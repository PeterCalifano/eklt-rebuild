/// @file patch.h
/// @brief Declares the ROS1 adapter for the native photometric patch state.
/// @details Event conversion and ROS timestamps stay here; bounded buffering,
///          warping, and event-frame accumulation are owned by `eklt_core`.

#pragma once

#include <dvs_msgs/Event.h>
#include <opencv2/core.hpp>
#include <ros/ros.h>

#include "eklt_core/photometric_patch_tracker.h"

namespace tracker
{

    /// @brief Adds ROS timestamps and display metadata to a native EKLT patch.
    struct Patch : public eklt_core::SPhotometricPatch
    {
        /// @brief Construct a live patch around an initialized feature.
        /// @param center Initial feature center in image coordinates.
        /// @param t_init Timestamp of the initialization image.
        Patch(const cv::Point2d &center, const ros::Time &t_init);

        /// @brief Construct a sentinel retired patch slot.
        Patch();

        /// @brief Convert and insert one ROS1 event into the native bounded buffer.
        /// @param event Event already known to overlap the patch.
        void insert(const dvs_msgs::Event &event);

        /// @brief Build the native event frame and synchronize the ROS timestamp.
        /// @param event_frame Output signed event frame.
        /// @return True when the frame contains a nonzero observation.
        bool getEventFramesAndReset(cv::Mat &event_frame);

        /// @brief Reinitialize this slot around a new feature.
        /// @param init_center New feature center.
        /// @param t New initialization timestamp.
        void reset(const cv::Point2d &init_center, const ros::Time &t);

        /// @brief Preserve the legacy reference-output warp helper.
        /// @param unwarped Input reference-frame point.
        /// @param warped Output point after applying the inverse patch warp.
        void warpPixel(const cv::Point2d &unwarped, cv::Point2d &warped) const;

        using eklt_core::SPhotometricPatch::warpPixel;

        /// @brief Exact ROS timestamp of the initialization image.
        ros::Time t_init_;

        /// @brief ROS timestamp synchronized with the native microsecond state.
        ros::Time t_curr_;

        /// @brief Stable display color used by the ROS1 viewer.
        cv::Scalar color_;
    };

} // namespace tracker
