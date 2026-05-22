#pragma once

#include <ceres/ceres.h>
#include <ceres/cubic_interpolation.h>
#include <opencv2/core/core.hpp>

#include "types.h"

namespace nlls
{
    /**
     * @brief Immutable residual-evaluation context for one patch optimization.
     *
     * The Ceres functor uses this object to access the current feature location,
     * initial feature location, event frame, and interpolated reference-image
     * gradient while evaluating equation (7) from the EKLT paper.
     */
    struct CostFunctionConfig
    {
        /**
         * @brief Construct residual context for a single event-frame patch.
         * @param feature Current feature center.
         * @param init_feature Feature center in the reference image.
         * @param event_frame Patch event frame used as optimizer observation.
         * @param grad_interp Interpolator over the reference image gradient.
         */
        CostFunctionConfig(cv::Point2d feature,
                           cv::Point2d init_feature,
                           const cv::Mat *event_frame,
                           Interpolator *grad_interp)
            : feature_(feature), event_frame_(event_frame), grad_interp_(grad_interp), init_feature_(init_feature)
        {
            patch_size_ = event_frame_->size[0];
            half_size_ = (event_frame_->size[0] - 1) / 2;
            size_ = patch_size_ * patch_size_;
            norm_event_frame_ = cv::norm(*event_frame_);
        }

        /**
         * @brief Current feature center.
         */
        cv::Point2d feature_;

        /**
         * @brief Feature center in the reference image.
         */
        cv::Point2d init_feature_;

        /**
         * @brief Event-frame observation for the current patch.
         */
        const cv::Mat *event_frame_;

        /**
         * @brief Square patch side length in pixels.
         */
        int patch_size_;

        /**
         * @brief Half of the square patch side length in pixels.
         */
        int half_size_;

        /**
         * @brief Number of residuals in the patch.
         */
        int size_;

        /**
         * @brief Legacy image-height field retained in the residual config layout.
         */
        int height_;

        /**
         * @brief Legacy image-width field retained in the residual config layout.
         */
        int width_;

        /**
         * @brief Bicubic interpolator over reference-image gradients.
         */
        Interpolator *grad_interp_;

        /**
         * @brief Norm used to normalize the event-frame residual term.
         */
        double norm_event_frame_;
    };

    /**
     * @brief Ceres autodiff functor implementing EKLT equation (7).
     *
     * Parameters are the local patch rotation/translation and optical-flow
     * direction. Residuals compare the warped image-gradient projection against the
     * event-frame observation.
     */
    struct ErrorRotation
    {

        /**
         * @brief Construct a residual functor using shared residual context.
         * @param config Residual context used during evaluation.
         */
        ErrorRotation(CostFunctionConfig *config) : config_(config) {}

        /**
         * @brief Extract rotation and translation parameters from a warp matrix.
         * @param p Output parameter vector [rotation, tx, ty].
         * @param warp Homogeneous 2D warp matrix.
         */
        static void getP0(double p[], const cv::Mat &warp)
        {
            p[0] = std::atan2(warp.at<double>(1, 0), warp.at<double>(0, 0));
            p[1] = warp.at<double>(0, 2);
            p[2] = warp.at<double>(1, 2);
        }

        /**
         * @brief Convert rotation and translation parameters to a warp matrix.
         * @param p0 Input parameter vector [rotation, tx, ty].
         * @param warp Output homogeneous 2D warp matrix.
         */
        static void getWarp(double p0[], cv::Mat &warp)
        {
            warp = (cv::Mat_<double>(3, 3) << std::cos(p0[0]), -std::sin(p0[0]), p0[1],
                    std::sin(p0[0]), std::cos(p0[0]), p0[2],
                    0, 0, 1);
        }

        /**
         * @brief Evaluate normalized EKLT residuals for Ceres autodiff.
         * @tparam T Ceres scalar type.
         * @param p Rotation and translation parameter block.
         * @param v Optical-flow direction parameter block.
         * @param residual Output residual vector, one value per patch pixel.
         * @return Always true for Ceres.
         */
        template <typename T>
        bool operator()(const T *p, const T *v, T *residual) const
        {
            // warp image gradient
            T norm_sq(1e-3);
            warp(p, v, residual, norm_sq);

            // compute loss function in equation (7) of the paper
            // we need to do 2 passes since we need to normalize by the gradient
            for (int i = 0; i < config_->size_; i++)
            {
                residual[i] = residual[i] / ceres::sqrt(norm_sq) +
                              config_->event_frame_->at<double>(i / config_->patch_size_, i % config_->patch_size_) / config_->norm_event_frame_;
            }
            return true;
        }

        /**
         * @brief Warp and project reference gradients into the optical-flow direction.
         * @tparam T Ceres scalar type.
         * @param p Rotation and translation parameter block.
         * @param v Optical-flow direction parameter block.
         * @param residual Output gradient-projection image flattened row-major.
         * @param norm_sq Accumulated squared norm of the gradient-projection image.
         */
        template <typename T>
        void warp(const T *p, const T *v, T *residual, T &norm_sq) const
        {
            // remap the image gradient according to equation (4)
            const T &r = p[0], tx = p[1], ty = p[2];

            T vx = ceres::cos(v[0]);
            T vy = ceres::sin(v[0]);

            T a0 = ceres::cos(p[0]);
            T a1 = -ceres::sin(p[0]);

            T a2 = -a1;
            T a3 = a0;

            for (int y = 0; y < config_->patch_size_; y++)
            {
                for (int x = 0; x < config_->patch_size_; x++)
                {
                    T x_p = a0 * T(x) + a1 * T(y) + a0 * (config_->feature_.x - config_->half_size_) + a1 * (config_->feature_.y - config_->half_size_) + p[1];
                    T y_p = a2 * T(x) + a3 * T(y) + a2 * (config_->feature_.x - config_->half_size_) + a3 * (config_->feature_.y - config_->half_size_) + p[2];

                    T g[2];
                    config_->grad_interp_->Evaluate(y_p, x_p, g);
                    residual[x + config_->patch_size_ * y] = g[0] * vx + g[1] * vy;
                    norm_sq += ceres::pow(residual[x + config_->patch_size_ * y], 2);
                }
            }
        }

        /**
         * @brief Residual context used during evaluation.
         */
        CostFunctionConfig *config_;
    };

    /**
     * @brief Factory for Ceres cost functions used by the EKLT optimizer.
     */
    struct Generator
    {
        /**
         * @brief Allocate an autodiff cost function for one patch optimization.
         * @param feature Current feature center.
         * @param init_feature Feature center in the reference image.
         * @param event_frame Event-frame observation.
         * @param grad_interp Reference-gradient interpolator.
         * @param functor Output pointer to the allocated functor owned by Ceres.
         * @return Newly allocated Ceres cost function.
         */
        static ceres::CostFunction *Create(cv::Point2d feature,
                                           cv::Point2d init_feature,
                                           const cv::Mat *event_frame,
                                           Interpolator *grad_interp,
                                           ErrorRotation *&functor)
        {
            CostFunctionConfig *config = new CostFunctionConfig(feature, init_feature, event_frame, grad_interp);
            functor = new ErrorRotation(config);
            int size = pow(event_frame->size[0], 2);
            return new ceres::AutoDiffCostFunction<ErrorRotation, ceres::DYNAMIC, 3, 1>(functor, size);
        }
    };

} // nlls
