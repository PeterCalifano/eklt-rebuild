#pragma once

#include <deque>

#include <ceres/ceres.h>
#include <ceres/cubic_interpolation.h>
#include <dvs_msgs/Event.h>
#include <opencv2/core.hpp>
#include <ros/ros.h>

namespace tracker
{

    /**
     * @brief Per-feature event patch tracked by EKLT.
     */
    struct Patch;

    /**
     * @brief Collection of active and lost feature patches.
     */
    using Patches = std::vector<Patch>;

    /**
     * @brief Queue of DVS events ordered by timestamp before tracker processing.
     */
    using EventBuffer = std::deque<dvs_msgs::Event>;

    /**
     * @brief Grayscale frame buffer indexed by ROS timestamp.
     */
    using ImageBuffer = std::map<ros::Time, cv::Mat>;

} // namespace tracker

namespace viewer
{

    /**
     * @brief Snapshot of feature state consumed by the asynchronous viewer.
     */
    struct FeatureTrackData
    {
        /**
         * @brief Feature patches to draw on the preview image.
         */
        tracker::Patches patches;

        /**
         * @brief Current tracker timestamp and initial feature timestamp.
         */
        ros::Time t, t_init;

        /**
         * @brief Source frame used as the visualization background.
         */
        cv::Mat image;
    };

} // namespace viewer

namespace nlls
{

    /**
     * @brief Ceres grid containing image-gradient samples for one reference frame.
     */
    using Grid = ceres::Grid2D<double, 2>;

    /**
     * @brief Owning pointer alias for gradient grids.
     */
    using GridPtr = std::unique_ptr<Grid>;

    /**
     * @brief Bicubic interpolator over a gradient grid.
     */
    using Interpolator = ceres::BiCubicInterpolator<Grid>;

    /**
     * @brief Owning pointer alias for gradient interpolators.
     */
    using InterpolatorPtr = std::unique_ptr<ceres::BiCubicInterpolator<Grid>>;

    /**
     * @brief Cached gradient interpolation data shared by patches from one reference frame.
     *
     * The optimizer stores one datum per reference image timestamp. Patches using
     * that timestamp share the Ceres grid and interpolator until @ref ref_counter_
     * reaches zero.
     */
    struct OptimizerDatum
    {
        /**
         * @brief Construct an empty datum.
         */
        OptimizerDatum() {}

        /**
         * @brief Construct interpolation helpers over flattened gradient data.
         * @param grad Flattened row-major gradient values.
         * @param img Reference image whose size defines the interpolation grid.
         * @param num_patches Number of patches initially sharing this datum.
         */
        OptimizerDatum(std::vector<double> &grad, cv::Mat &img, int num_patches)
        {
            grad_ = grad;
            grad_grid_ = new nlls::Grid(grad_.data(), 0, img.rows, 0, img.cols);
            grad_interp_ = new nlls::Interpolator(*grad_grid_);
            ref_counter_ = num_patches;
        }

        /**
         * @brief Release Ceres interpolation helpers owned by this datum.
         */
        void clear()
        {
            delete grad_interp_;
            delete grad_grid_;
        }

        /**
         * @brief Backing storage for @ref grad_grid_.
         */
        std::vector<double> grad_;

        /**
         * @brief Ceres grid view into @ref grad_.
         */
        nlls::Grid *grad_grid_;

        /**
         * @brief Bicubic interpolator used by residual evaluation.
         */
        nlls::Interpolator *grad_interp_;

        /**
         * @brief Number of active patches still using this cached datum.
         */
        int ref_counter_;
    };

    /**
     * @brief Optimizer cache indexed by reference image timestamp.
     */
    using OptimizerData = std::map<ros::Time, OptimizerDatum>;

} // namespace nlls
