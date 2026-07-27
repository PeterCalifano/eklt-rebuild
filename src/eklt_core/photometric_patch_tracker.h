/// @file photometric_patch_tracker.h
/// @brief Defines ROS-free asynchronous photometric patch tracking.
/// @details The tracker-side data model accumulates signed events into local
///          frames and directly owns the required Ceres optimization state.

#ifndef EKLT_CORE_PHOTOMETRIC_PATCH_TRACKER_H_
#define EKLT_CORE_PHOTOMETRIC_PATCH_TRACKER_H_

#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <vector>

#include <ceres/ceres.h>
#include <ceres/cubic_interpolation.h>
#include <opencv2/core.hpp>

namespace eklt_core
{

    /// @brief One ROS-free event sample used by the photometric tracker.
    struct SEventSample
    {
        /// @brief Sensor x coordinate in pixels.
        uint16_t x{0};
        /// @brief Sensor y coordinate in pixels.
        uint16_t y{0};
        /// @brief Signed event polarity.
        int8_t p{1};
        /// @brief Absolute event timestamp in microseconds.
        int64_t t_us{0};
    };

    /// @brief Mutable state and bounded event buffer for one tracked feature.
    struct SPhotometricPatch
    {
        /// @brief Construct an empty patch state.
        SPhotometricPatch();

        /// @brief Construct a patch around one initialized feature.
        /// @param id Stable feature identifier.
        /// @param center Initial center in image coordinates.
        /// @param t_us Initialization timestamp in microseconds.
        /// @param patch_size Odd patch width and height.
        /// @param batch_size Maximum buffered event count.
        /// @param update_rate Minimum new-event count between updates.
        /// @throws std::invalid_argument If `patch_size` is not positive and odd.
        SPhotometricPatch(int id,
                          const cv::Point2d &center,
                          int64_t t_us,
                          int patch_size,
                          int batch_size,
                          int update_rate);

        /// @brief Check whether a sensor coordinate lies inside the current patch.
        /// @return True when the coordinate is inside the current patch.
        bool contains(double x, double y) const;

        /// @brief Insert the newest event while preserving the bounded buffer.
        /// @param event Event to place at the front of the buffer.
        void insert(const SEventSample &event);

        /// @brief Check whether both batch and update-rate thresholds are met.
        /// @return True when the patch is ready for optimization.
        bool readyForUpdate() const;

        /// @brief Apply the inverse current warp to a pixel.
        /// @param unwarped Reference pixel.
        /// @param warped Output pixel; ignored when null.
        void warpPixel(const cv::Point2d &unwarped,
                       cv::Point2d *warped) const;

        /// @brief Accumulate buffered events into a bilinearly sampled local frame.
        /// @param event_frame Output `CV_64F` signed event frame.
        /// @return True when the accumulated frame has nonzero norm.
        /// @details Resets only the new-event counter; the bounded buffer remains
        ///          available for overlapping updates.
        bool getEventFrameAndReset(cv::Mat *event_frame);

      public:
        // PUBLIC DATA MEMBERS

        /// @brief Stable feature identifier.
        int id{0};
        /// @brief Feature center at patch initialization.
        cv::Point2d init_center;
        /// @brief Current warped feature center.
        cv::Point2d center;
        /// @brief Absolute initialization timestamp in microseconds.
        int64_t t_init_us{0};
        /// @brief Absolute timestamp of the latest accumulated event frame.
        int64_t t_curr_us{0};
        /// @brief Half-width of the square patch in pixels.
        int half_size{0};
        /// @brief Maximum number of retained events.
        int batch_size{1};
        /// @brief Minimum new-event count between updates.
        int update_rate{1};
        /// @brief Number of events inserted since the previous update.
        int event_counter{0};
        /// @brief Current optical-flow direction in radians.
        double flow_angle{0.0};
        /// @brief Solver-derived tracking-quality score.
        double tracking_quality{1.0};
        /// @brief Whether the optical-flow bootstrap has completed.
        bool initialized{false};
        /// @brief Whether the patch is no longer eligible for optimization.
        bool lost{false};
        /// @brief Current homogeneous rigid patch warp.
        cv::Mat warping;
        /// @brief Horizontal initialization-image gradient.
        cv::Mat gradient_x;
        /// @brief Vertical initialization-image gradient.
        cv::Mat gradient_y;
        /// @brief Newest-first bounded event window.
        std::deque<SEventSample> event_buffer;

      private:
        static void addBilinear(cv::Mat *frame,
                                int x,
                                int y,
                                double value);
    };

    /// @brief Optimizes photometric patch warp and optical-flow direction with Ceres.
    /// @details Owns solver configuration and timestamped gradient caches
    ///          directly. Ceres is a required `eklt-rebuild` dependency.
    class CPhotometricOptimizer
    {
      public:
        /// @brief Construct a deterministic per-patch Ceres optimizer.
        /// @param max_num_iterations Maximum Ceres iterations per patch update.
        explicit CPhotometricOptimizer(int max_num_iterations = 10);

        /// @brief Transfer ownership of solver and gradient-cache state.
        /// @param other Optimizer whose state is transferred.
        CPhotometricOptimizer(CPhotometricOptimizer &&other) noexcept = default;

        /// @brief Transfer ownership of solver and gradient-cache state.
        /// @param other Optimizer whose state is transferred.
        /// @return This optimizer after taking ownership.
        CPhotometricOptimizer &operator=(CPhotometricOptimizer &&other) noexcept = default;

        /// @brief Disable copying because cached Ceres interpolation owns storage.
        CPhotometricOptimizer(const CPhotometricOptimizer &) = delete;

        /// @brief Disable copying because cached Ceres interpolation owns storage.
        CPhotometricOptimizer &operator=(const CPhotometricOptimizer &) = delete;

        /// @brief Cache interpolated log-image gradients for initialized patches.
        /// @param image Single-channel initialization image.
        /// @param t_us Cache key in absolute microseconds.
        /// @param ref_counter Number of patch references associated with the image.
        /// @throws std::invalid_argument If `image` is not a non-empty,
        ///         single-channel 2D matrix or `ref_counter` is nonpositive.
        void precomputeGradientImage(const cv::Mat &image,
                                     int64_t t_us,
                                     int ref_counter);

        /// @brief Release one patch reference to a cached gradient image.
        /// @param t_us Absolute timestamp identifying the cached image.
        /// @return True when a matching cache reference was released.
        /// @details The cache is erased after its final reference is released.
        bool releaseGradientImageReference(int64_t t_us);

        /// @brief Optimize one patch against its cached initialization gradients.
        /// @param event_frame Signed local event accumulation.
        /// @param patch Mutable patch state.
        /// @return True when Ceres reports a usable solution.
        bool optimize(const cv::Mat &event_frame,
                      SPhotometricPatch *patch);

        /// @brief Compute normalized log-image Sobel gradients.
        /// @param image Single-channel source image.
        /// @param I_x Output horizontal gradient.
        /// @param I_y Output vertical gradient.
        static void computeLogGradients(const cv::Mat &image,
                                        cv::Mat *I_x,
                                        cv::Mat *I_y);

        /// @brief Bootstrap optical-flow direction from local gradients and events.
        /// @param patch Patch containing initialization gradients.
        /// @param event_frame Signed local event frame.
        static void bootstrapFlowFromEventFrame(SPhotometricPatch *patch,
                                                const cv::Mat &event_frame);

        /// @brief Compute the gradient-driven event batch size.
        /// @param I_x Horizontal patch gradient.
        /// @param I_y Vertical patch gradient.
        /// @param flow_angle Current optical-flow direction in radians.
        /// @param displacement_px Target pixel displacement.
        /// @param max_batch_size Configured upper bound.
        /// @return Batch size clamped to at least five events and the upper bound.
        static int computeAdaptiveBatchSize(const cv::Mat &I_x,
                                            const cv::Mat &I_y,
                                            double flow_angle,
                                            double displacement_px,
                                            int max_batch_size);

      private:
        using TGradientGrid = ceres::Grid2D<double, 2>;
        using TGradientInterpolator = ceres::BiCubicInterpolator<TGradientGrid>;

        /// @brief Own one flattened gradient field and its non-owning Ceres views.
        /// @details Declaration order keeps gradient storage alive for the grid
        ///          and keeps the grid alive for the interpolator.
        struct SGradientCache
        {
            SGradientCache();
            SGradientCache(const std::vector<double> &gradient_values,
                           int rows,
                           int columns,
                           int reference_count);

            std::vector<double> gradient_values;
            std::unique_ptr<TGradientGrid> grid;
            std::unique_ptr<TGradientInterpolator> interpolator;
            int reference_count{0};
        };

        ceres::Solver::Options solver_options_;
        std::map<int64_t, SGradientCache> gradients_;
    };

} // namespace eklt_core

#endif // EKLT_CORE_PHOTOMETRIC_PATCH_TRACKER_H_
