#pragma once

#include <ros/ros.h>

#include "error.h"
#include "patch.h"
#include "types.h"

namespace nlls
{

    /**
     * @brief Nonlinear optimizer for EKLT patch warp and optical-flow updates.
     *
     * The optimizer caches log-image gradients per reference frame, builds Ceres
     * residuals for each event frame, and updates the patch transform and flow
     * direction used by the tracker.
     */
    struct Optimizer
    {
        /**
         * @brief Configure Ceres solver options and patch-size-dependent state.
         */
        Optimizer();

        /**
         * @brief Release optimizer-owned Ceres resources.
         */
        ~Optimizer();

        /**
         * @brief Drop one patch reference to cached data for a timestamp.
         * @param time Reference-image timestamp whose cache counter is decremented.
         *
         * When no active patches still use the timestamp, the cached gradient grid
         * and interpolator are released.
         */
        void decrementCounter(ros::Time &time);

        /**
         * @brief Compute gradients of a log-intensity image.
         * @param img Input grayscale image.
         * @param I_x Output horizontal log-gradient image.
         * @param I_y Output vertical log-gradient image.
         */
        void getLogGradients(const cv::Mat &img, cv::Mat &I_x, cv::Mat &I_y);

        /**
         * @brief Precompute and cache gradient interpolation data for one image.
         * @param patches Patches initialized from the image.
         * @param image_it Iterator to the image and timestamp.
         * @return True when cache data was generated or already available.
         */
        bool precomputeLogImageArray(const tracker::Patches &patches, const tracker::ImageBuffer::iterator &image_it);

        /**
         * @brief Optimize patch warp and optical-flow direction from an event frame.
         * @param event_frame Patch event frame from recent events.
         * @param patch Patch state updated in-place.
         */
        void optimizeParameters(const cv::Mat &event_frame, tracker::Patch &patch);

        /**
         * @brief Ceres problem construction options.
         */
        ceres::Problem::Options prob_options;

        /**
         * @brief Ceres solver options shared by patch updates.
         */
        ceres::Solver::Options solver_options;

        /**
         * @brief Robust loss used by the EKLT residuals.
         */
        ceres::LossFunction *loss_function;

        /**
         * @brief Cached gradient interpolation data indexed by reference timestamp.
         */
        OptimizerData optimizer_data_;

        /**
         * @brief Current square patch side length in pixels.
         */
        int patch_size_;

        /**
         * @brief Last constructed Ceres cost function.
         */
        ceres::CostFunction *cost_function_;
    };

} // namespace nlls
