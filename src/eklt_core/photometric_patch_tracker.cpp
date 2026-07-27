/// @file photometric_patch_tracker.cpp
/// @brief Implements ROS-free asynchronous photometric patch tracking.
/// @details Implements Ceres interpolation, residual evaluation, and direct
///          optimizer-state coordination.

#include "eklt_core/photometric_patch_tracker.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <stdexcept>
#include <utility>
#include <vector>

#include <ceres/ceres.h>
#include <ceres/cubic_interpolation.h>
#include <opencv2/imgproc.hpp>

#include "eklt_core/image_normalization.h"

namespace eklt_core
{
    namespace
    {

        using TGrid = ceres::Grid2D<double, 2>;
        using TInterpolator = ceres::BiCubicInterpolator<TGrid>;

        /// @brief Non-owning residual context shared by all autodiff evaluations.
        /// @details Carries patch geometry, normalized event data, and the cached
        ///          image-gradient interpolator without copying solver inputs.
        struct SPhotometricErrorContext
        {
            /// @brief Bind one event frame to its reference-image gradient field.
            /// @param feature Current feature center.
            /// @param init_feature Feature center in the reference image.
            /// @param event_frame Signed local event accumulation.
            /// @param grad_interp Cached two-channel gradient interpolator.
            SPhotometricErrorContext(cv::Point2d feature,
                                     cv::Point2d init_feature,
                                     const cv::Mat *event_frame,
                                     TInterpolator *grad_interp)
                : feature(feature),
                  init_feature(init_feature),
                  event_frame(event_frame),
                  patch_size(event_frame->rows),
                  half_size((event_frame->rows - 1) / 2),
                  size(event_frame->rows * event_frame->cols),
                  grad_interp(grad_interp),
                  norm_event_frame(std::max(cv::norm(*event_frame), 1e-6))
            {
            }

            cv::Point2d feature;
            cv::Point2d init_feature;
            const cv::Mat *event_frame{nullptr};
            int patch_size{0};
            int half_size{0};
            int size{0};
            TInterpolator *grad_interp{nullptr};
            double norm_event_frame{1.0};
        };

        /// @brief Ceres residual functor for rigid patch and flow-direction fitting.
        struct CPhotometricError
        {
            explicit CPhotometricError(const SPhotometricErrorContext &context) : context(context) {}

            /// @brief Evaluate normalized predicted-versus-measured event residuals.
            template <typename T>
            bool operator()(const T *p, const T *v, T *residual) const
            {
                // Normalize the predicted gradient response before combining
                // it with the measured signed event frame.
                T norm_sq(1e-3);
                warp(p, v, residual, norm_sq);
                for (int i = 0; i < context.size; ++i)
                {
                    residual[i] =
                        residual[i] / ceres::sqrt(norm_sq) +
                        T(context.event_frame->at<double>(i / context.patch_size, i % context.patch_size) /
                          context.norm_event_frame);
                }
                return true;
            }

            /// @brief Project interpolated image gradients through one rigid warp.
            template <typename T>
            void warp(const T *p, const T *v, T *residual, T &norm_sq) const
            {
                // Evaluate the cached two-channel gradient at every rigidly
                // warped patch coordinate and project it onto the flow vector.
                const T vx = ceres::cos(v[0]);
                const T vy = ceres::sin(v[0]);
                const T a0 = ceres::cos(p[0]);
                const T a1 = -ceres::sin(p[0]);
                const T a2 = -a1;
                const T a3 = a0;

                for (int y = 0; y < context.patch_size; ++y)
                {
                    for (int x = 0; x < context.patch_size; ++x)
                    {
                        const T x_p = a0 * T(x) + a1 * T(y) +
                                      a0 * T(context.feature.x - context.half_size) +
                                      a1 * T(context.feature.y - context.half_size) + p[1];
                        const T y_p = a2 * T(x) + a3 * T(y) +
                                      a2 * T(context.feature.x - context.half_size) +
                                      a3 * T(context.feature.y - context.half_size) + p[2];

                        T g[2];
                        context.grad_interp->Evaluate(y_p, x_p, g);
                        residual[x + context.patch_size * y] = g[0] * vx + g[1] * vy;
                        norm_sq += ceres::pow(residual[x + context.patch_size * y], 2);
                    }
                }
            }

            SPhotometricErrorContext context;
        };

        using TPhotometricCostFunction =
            ceres::AutoDiffCostFunction<CPhotometricError, ceres::DYNAMIC, 3, 1>;

        /// @brief Decode the planar rigid-warp parameters used by Ceres.
        /// @param p Output rotation and translation parameters.
        /// @param warp Homogeneous patch warp.
        void getP0(double p[], const cv::Mat &warp)
        {
            p[0] = std::atan2(warp.at<double>(1, 0), warp.at<double>(0, 0));
            p[1] = warp.at<double>(0, 2);
            p[2] = warp.at<double>(1, 2);
        }

        /// @brief Encode optimized planar parameters as a homogeneous warp.
        /// @param p0 Rotation and translation parameters.
        /// @param warp Output homogeneous patch warp.
        void getWarp(const double p0[], cv::Mat *warp)
        {
            *warp = (cv::Mat_<double>(3, 3) << std::cos(p0[0]), -std::sin(p0[0]), p0[1],
                     std::sin(p0[0]), std::cos(p0[0]), p0[2],
                     0, 0, 1);
        }

    } // namespace

    CPhotometricOptimizer::SGradientCache::SGradientCache() = default;

    CPhotometricOptimizer::SGradientCache::SGradientCache(const std::vector<double> &gradient_values,
                                                          int rows,
                                                          int columns,
                                                          int reference_count)
        : gradient_values(gradient_values), reference_count(reference_count)
    {
        grid.reset(new TGradientGrid(this->gradient_values.data(),
                                     0, rows, 0, columns));
        interpolator.reset(new TGradientInterpolator(*grid));
    }

    SPhotometricPatch::SPhotometricPatch() = default;

    SPhotometricPatch::SPhotometricPatch(int id,
                                         const cv::Point2d &center,
                                         int64_t t_us,
                                         int patch_size,
                                         int batch_size,
                                         int update_rate)
        : id(id),
          init_center(center),
          center(center),
          t_init_us(t_us),
          t_curr_us(t_us),
          half_size(patch_size > 0 ? (patch_size - 1) / 2 : 0),
          batch_size(std::max(1, batch_size)),
          update_rate(std::max(1, update_rate)),
          warping(cv::Mat::eye(3, 3, CV_64F))
    {
        // Preserve an unambiguous integer center pixel and symmetric patch
        // geometry for accumulation and optimization.
        if (patch_size <= 0 || patch_size % 2 == 0)
        {
            throw std::invalid_argument("photometric patch size must be positive and odd");
        }
    }

    bool SPhotometricPatch::contains(double x, double y) const
    {
        // Test against the current warped center while retaining the fixed
        // initialization patch extent.
        return half_size >= std::abs(x - center.x) && half_size >= std::abs(y - center.y);
    }

    void SPhotometricPatch::insert(const SEventSample &event)
    {
        // Keep newest-first ordering while retaining only the configured
        // optimization window.
        event_buffer.push_front(event);
        if (static_cast<int>(event_buffer.size()) > batch_size)
        {
            event_buffer.pop_back();
        }
        if (event_counter < std::numeric_limits<int>::max())
        {
            ++event_counter;
        }
    }

    bool SPhotometricPatch::readyForUpdate() const
    {
        // Require a full optimization window and enough events since the
        // previous update, including configurations whose rate exceeds it.
        const int update_threshold = std::min(update_rate, batch_size);
        return static_cast<int>(event_buffer.size()) >= batch_size && event_counter >= update_threshold;
    }

    void SPhotometricPatch::warpPixel(const cv::Point2d &unwarped,
                                      cv::Point2d *warped) const
    {
        if (warped == nullptr)
        {
            return;
        }

        // Apply the inverse stored transform because callers supply coordinates
        // in the initialization-image frame.
        const cv::Mat W = warping.inv();
        warped->x = W.at<double>(0, 0) * unwarped.x + W.at<double>(0, 1) * unwarped.y + W.at<double>(0, 2);
        warped->y = W.at<double>(1, 0) * unwarped.x + W.at<double>(1, 1) * unwarped.y + W.at<double>(1, 2);
    }

    bool SPhotometricPatch::getEventFrameAndReset(cv::Mat *event_frame)
    {
        // At least two events are required because accumulation uses
        // consecutive samples from the bounded event window.
        if (event_frame == nullptr || event_buffer.size() < 2U)
        {
            return false;
        }

        const int size = 2 * half_size + 1;
        *event_frame = cv::Mat::zeros(size, size, CV_64F);
        const int iterations = std::min<int>(batch_size, static_cast<int>(event_buffer.size())) - 1;
        if (iterations <= 0)
        {
            return false;
        }

        // Bilinearly accumulate signed events in patch-local coordinates so
        // subpixel locations contribute smoothly to neighboring pixels.
        for (int i = 0; i < iterations; ++i)
        {
            const SEventSample &event = event_buffer[static_cast<std::size_t>(i)];
            if (!contains(event.x, event.y))
            {
                continue;
            }

            const double local_x = static_cast<double>(event.x) - center.x + half_size;
            const double local_y = static_cast<double>(event.y) - center.y + half_size;
            const int x0 = static_cast<int>(std::floor(local_x));
            const int y0 = static_cast<int>(std::floor(local_y));
            const double rx = local_x - x0;
            const double ry = local_y - y0;
            const double polarity = event.p > 0 ? 1.0 : -1.0;
            addBilinear(event_frame, x0 + 1, y0 + 1, polarity * rx * ry);
            addBilinear(event_frame, x0 + 1, y0, polarity * rx * (1.0 - ry));
            addBilinear(event_frame, x0, y0 + 1, polarity * (1.0 - rx) * ry);
            addBilinear(event_frame, x0, y0, polarity * (1.0 - rx) * (1.0 - ry));
        }

        // Compute the midpoint in extended precision so absolute timestamps
        // near the int64 limits cannot overflow during addition.
        const long double newest_t_us = event_buffer.front().t_us;
        const long double oldest_t_us = event_buffer[static_cast<std::size_t>(iterations)].t_us;
        t_curr_us = static_cast<int64_t>((newest_t_us + oldest_t_us) / 2.0L);
        event_counter = 0;
        return cv::norm(*event_frame) > 0.0;
    }

    void SPhotometricPatch::addBilinear(cv::Mat *frame,
                                        int x,
                                        int y,
                                        double value)
    {
        if (x < 0 || y < 0 || x >= frame->cols || y >= frame->rows)
        {
            return;
        }

        // Accumulate only the in-bounds portion of a bilinear footprint so
        // border events cannot address storage outside the local frame.
        frame->at<double>(y, x) += value;
    }

    CPhotometricOptimizer::CPhotometricOptimizer(int max_num_iterations)
    {
        // Use a deterministic single-threaded dense solve because each
        // optimization operates on one small independent patch.
        solver_options_.minimizer_progress_to_stdout = false;
        solver_options_.num_threads = 1;
        solver_options_.linear_solver_type = ceres::DENSE_QR;
        solver_options_.logging_type = ceres::SILENT;
        solver_options_.max_num_iterations = max_num_iterations;
        solver_options_.use_nonmonotonic_steps = true;
    }

    void CPhotometricOptimizer::precomputeGradientImage(const cv::Mat &image,
                                                        int64_t t_us,
                                                        int ref_counter,
                                                        double log_eps)
    {
        // A cache without an owning patch could never receive a balanced
        // release, so reject it before allocating gradient storage.
        if (ref_counter <= 0)
        {
            throw std::invalid_argument("photometric optimizer reference count "
                                        "must be positive");
        }

        // Reject storage that cannot provide one scalar initialization
        // gradient at every image coordinate.
        if (image.empty() || image.dims != 2 || image.channels() != 1)
        {
            throw std::invalid_argument("photometric optimizer image must be non-empty and single-channel");
        }
        if (!std::isfinite(log_eps) || log_eps <= 0.0)
        {
            throw std::invalid_argument(
                "photometric optimizer log offset must be finite and positive");
        }

        // Flatten the two gradient channels in row-major pixel order for Ceres
        // Grid2D interpolation.
        cv::Mat I_x;
        cv::Mat I_y;
        computeLogGradients(image, &I_x, &I_y, log_eps);
        std::vector<double> grad;
        grad.reserve(static_cast<std::size_t>(image.rows) *
                     static_cast<std::size_t>(image.cols) * 2U);
        for (int row = 0; row < image.rows; ++row)
        {
            for (int col = 0; col < image.cols; ++col)
            {
                grad.push_back(I_x.at<double>(row, col));
                grad.push_back(I_y.at<double>(row, col));
            }
        }

        // Cache interpolation state under the absolute initialization timestamp
        // shared by all patches derived from this image.
        gradients_[t_us] =
            SGradientCache(grad, image.rows, image.cols, ref_counter);
    }

    bool CPhotometricOptimizer::releaseGradientImageReference(int64_t t_us)
    {
        std::map<int64_t, SGradientCache>::iterator cache_it =
            gradients_.find(t_us);
        if (cache_it == gradients_.end())
        {
            return false;
        }

        // Retain interpolation storage until every patch initialized from the
        // same image has released its reference.
        if (cache_it->second.reference_count > 1)
        {
            --cache_it->second.reference_count;
        }
        else
        {
            gradients_.erase(cache_it);
        }
        return true;
    }

    std::size_t CPhotometricOptimizer::gradientCacheCount() const
    {
        return gradients_.size();
    }

    bool CPhotometricOptimizer::optimize(const cv::Mat &event_frame,
                                         SPhotometricPatch *patch)
    {
        // Validate the complete patch/event-frame geometry before exposing its
        // storage to Ceres.
        if (patch == nullptr || event_frame.empty() || patch->lost ||
            event_frame.dims != 2 || event_frame.type() != CV_64F ||
            event_frame.rows != event_frame.cols ||
            event_frame.rows != 2 * patch->half_size + 1 ||
            patch->warping.rows != 3 || patch->warping.cols != 3 ||
            patch->warping.type() != CV_64F)
        {
            return false;
        }

        // Resolve the gradient field captured at patch initialization; a later
        // image must not silently replace this photometric reference.
        std::map<int64_t, SGradientCache>::iterator cache_it =
            gradients_.find(patch->t_init_us);
        if (cache_it == gradients_.end() || !cache_it->second.interpolator)
        {
            return false;
        }

        // Build one dynamic residual block from the current event frame and
        // solve for rigid warp plus optical-flow direction.
        ceres::Problem problem;
        ceres::Solver::Summary summary;
        double p0[3];
        getP0(p0, patch->warping);
        double v0[] = {patch->flow_angle};

        const SPhotometricErrorContext context(patch->center, patch->init_center, &event_frame,
                                               cache_it->second.interpolator.get());
        ceres::CostFunction *cost_function =
            new TPhotometricCostFunction(new CPhotometricError(context),
                                         event_frame.rows * event_frame.cols);
        problem.AddResidualBlock(cost_function, nullptr, p0, v0);
        ceres::Solve(solver_options_, &problem, &summary);

        // Preserve the prior patch state when Ceres cannot produce a usable,
        // finite solution.
        if (!summary.IsSolutionUsable() ||
            !std::isfinite(p0[0]) || !std::isfinite(p0[1]) ||
            !std::isfinite(p0[2]) || !std::isfinite(v0[0]) ||
            !std::isfinite(summary.final_cost))
        {
            return false;
        }

        // Commit the complete finite solution together so failed solves leave
        // the externally visible patch state unchanged.
        getWarp(p0, &patch->warping);
        const double two_pi = 6.283185307179586476925286766559;
        patch->flow_angle = std::fmod(v0[0], two_pi);
        patch->tracking_quality = 1.0 - summary.final_cost / 2.0;
        patch->warpPixel(patch->init_center, &patch->center);
        return true;
    }

    void CPhotometricOptimizer::computeLogGradients(const cv::Mat &image,
                                                    cv::Mat *I_x,
                                                    cv::Mat *I_y,
                                                    double log_eps)
    {
        // Null outputs and invalid source geometry cannot satisfy the two-plane
        // gradient contract.
        if (I_x == nullptr || I_y == nullptr)
        {
            return;
        }
        if (image.empty() || image.dims != 2 || image.channels() != 1 ||
            !std::isfinite(log_eps) || log_eps <= 0.0)
        {
            I_x->release();
            I_y->release();
            return;
        }

        // Normalize before the logarithm so frame-backed and reconstructed
        // images produce gradients on the same intensity scale.
        cv::Mat log_image;
        const cv::Mat normalized_image = NormalizeImageToUnitRange64(image);
        cv::log(normalized_image + log_eps, log_image);
        cv::Sobel(log_image / 8.0, *I_x, CV_64F, 1, 0, 3);
        cv::Sobel(log_image / 8.0, *I_y, CV_64F, 0, 1, 3);
    }

    void CPhotometricOptimizer::bootstrapFlowFromEventFrame(SPhotometricPatch *patch,
                                                            const cv::Mat &event_frame)
    {
        // Require matching double-precision gradient and event-frame planes
        // before forming the normal equations.
        if (patch == nullptr || patch->gradient_x.empty() ||
            patch->gradient_y.empty() || event_frame.empty() ||
            patch->gradient_x.type() != CV_64F ||
            patch->gradient_y.type() != CV_64F ||
            event_frame.type() != CV_64F ||
            patch->gradient_x.size() != patch->gradient_y.size() ||
            patch->gradient_x.size() != event_frame.size())
        {
            return;
        }

        // Accumulate the spatial and temporal gradient products used by the
        // local two-parameter optical-flow system.
        const cv::Mat &I_x = patch->gradient_x;
        const cv::Mat &I_y = patch->gradient_y;
        const double s_I_xx = cv::sum(I_x.mul(I_x))[0];
        const double s_I_yy = cv::sum(I_y.mul(I_y))[0];
        const double s_I_xy = cv::sum(I_x.mul(I_y))[0];
        const double s_I_xt = cv::sum(I_x.mul(event_frame))[0];
        const double s_I_yt = cv::sum(I_y.mul(event_frame))[0];

        // Solve with SVD so weakly conditioned patches fail cleanly without
        // introducing non-finite flow state.
        cv::Mat M = (cv::Mat_<double>(2, 2) << s_I_xx, s_I_xy, s_I_xy, s_I_yy);
        cv::Mat b = (cv::Mat_<double>(2, 1) << s_I_xt, s_I_yt);
        cv::Mat v;
        if (!cv::solve(M, -b, v, cv::DECOMP_SVD))
        {
            return;
        }

        // Publish the solved flow direction only after the local system reports
        // a usable velocity estimate.
        patch->flow_angle = std::atan2(v.at<double>(0, 0), v.at<double>(1, 0));
        patch->initialized = true;
    }

    int CPhotometricOptimizer::computeAdaptiveBatchSize(const cv::Mat &I_x,
                                                        const cv::Mat &I_y,
                                                        double flow_angle,
                                                        double displacement_px,
                                                        int max_batch_size)
    {
        // Clamp the configured ceiling to the minimum usable batch before
        // evaluating image-dependent adaptation.
        const int effective_max_batch_size = std::max(5, max_batch_size);
        if (I_x.empty() || I_y.empty() || I_x.size() != I_y.size())
        {
            return effective_max_batch_size;
        }

        // Project the spatial gradient onto the current flow direction and use
        // its L1 energy as the event-count demand.
        cv::Mat gradient =
            displacement_px * std::cos(flow_angle) * I_x +
            displacement_px * std::sin(flow_angle) * I_y;
        const double adaptive = std::floor(cv::norm(gradient, cv::NORM_L1));
        if (!std::isfinite(adaptive) ||
            adaptive >= static_cast<double>(effective_max_batch_size))
        {
            return effective_max_batch_size;
        }
        return std::max(5, static_cast<int>(adaptive));
    }

} // namespace eklt_core
