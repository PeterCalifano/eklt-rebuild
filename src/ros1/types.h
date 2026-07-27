/// @file types.h
/// @brief Defines ROS1-facing EKLT container and viewer data types.
/// @details ROS message and timestamp ownership remains in this compatibility
///          layer while patch computation is supplied by the ROS-free core.

#pragma once

#include <deque>
#include <map>
#include <vector>

#include <dvs_msgs/Event.h>
#include <opencv2/core.hpp>
#include <ros/ros.h>

#include "eklt_core/tracker_orchestrator.h"

namespace tracker
{

    /// @brief ROS1 adapter around one native photometric patch.
    struct Patch;

    /// @brief Collection of active and retired feature slots.
    using Patches = std::vector<Patch>;

    /// @brief Queue of DVS events ordered by timestamp before processing.
    using EventBuffer = std::deque<dvs_msgs::Event>;

    /// @brief Grayscale frame buffer indexed by ROS timestamp.
    using ImageBuffer = std::map<ros::Time, cv::Mat>;

} // namespace tracker

namespace viewer
{

    /// @brief Snapshot of feature state consumed by the asynchronous viewer.
    struct FeatureTrackData
    {
        /// @brief Owning native state rendered by the ROS1 publisher.
        eklt_core::STrackerSnapshot snapshot;

        /// @brief Current tracker timestamp.
        ros::Time t;

        /// @brief Initial timestamp used to zero the displayed elapsed time.
        ros::Time t_init;

    };

} // namespace viewer
