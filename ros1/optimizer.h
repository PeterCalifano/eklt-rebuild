/// @file optimizer.h
/// @brief Declares the ROS1 overlay optimizer adapter.
/// @details The adapter preserves established ROS1 method spellings while
///          delegating all gradients, caches, and Ceres solves to `eklt_core`.

#pragma once

#include <opencv2/core.hpp>
#include <ros/ros.h>

#include "eklt_core/photometric_patch_tracker.h"
#include "types.h"

namespace nlls
{

    /// @brief Compatibility adapter over `eklt_core::CPhotometricOptimizer`.
    class Optimizer
    {
      public:
        /// @brief Construct the native optimizer from the active ROS1 flags.
        Optimizer();

        /// @brief Release one patch reference to a cached initialization image.
        /// @param time ROS timestamp identifying the cached image.
        void decrementCounter(ros::Time &time);

        /// @brief Compute native log-intensity gradients with the ROS1 offset.
        /// @param image Input single-channel image.
        /// @param gradient_x Output horizontal gradient.
        /// @param gradient_y Output vertical gradient.
        void getLogGradients(const cv::Mat &image,
                             cv::Mat &gradient_x,
                             cv::Mat &gradient_y);

        /// @brief Cache an initialization image for its active ROS1 patches.
        /// @param patches Patches initialized from `image_it`.
        /// @param image_it Image and exact ROS timestamp.
        /// @return True when at least one active reference was cached.
        bool precomputeLogImageArray(const tracker::Patches &patches,
                                     const tracker::ImageBuffer::iterator &image_it);

        /// @brief Optimize a ROS1 patch through the native Ceres implementation.
        /// @param event_frame Signed local event observation.
        /// @param patch Patch updated in place.
        void optimizeParameters(const cv::Mat &event_frame,
                                tracker::Patch &patch);

      private:
        eklt_core::CPhotometricOptimizer optimizer_;
    };

} // namespace nlls
