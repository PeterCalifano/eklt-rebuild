/// @file fibar_adapters.h
/// @brief Declares Eigen-backed wrapper adapters for FIBAR reconstruction.
/// @details Co-located with their implementation, these C++ APIs own
///          generated-language dtype conversion without exposing ROS types or
///          placing wrapper-only policy in the algorithm core.

#ifndef WRAP_ADAPTERS_FIBAR_ADAPTERS_H_
#define WRAP_ADAPTERS_FIBAR_ADAPTERS_H_

#include <cstddef>
#include <cstdint>

#include "event_recon_fibar_core/fibar_reconstructor.h"
#include "wrap_adapters/GtsamAliases.h"

namespace wrap_adapters
{

    /**
     * @brief Adapts the core patch storage to Eigen matrices understood by gtwrap.
     */
    class CLocalFeaturePatchAdapter
    {
      public:
        /// @brief Construct an empty patch suitable for adapter-owned storage.
        CLocalFeaturePatchAdapter();

        /// @brief Copy one native patch into adapter-owned storage.
        /// @param patch Native patch to adapt.
        /// @throws std::invalid_argument If patch geometry, storage, or quality
        ///         metadata violates the native patch contract.
        explicit CLocalFeaturePatchAdapter(const event_recon_fibar_core::SLocalFeaturePatch &patch);

        /// @return Number of intensity samples in the patch.
        std::size_t size() const;
        /// @return Patch intensity as a row-major logical Eigen matrix.
        gtsam::Matrix intensity() const;
        /// @return Horizontal gradient as an Eigen matrix.
        gtsam::Matrix gradientX() const;
        /// @return Vertical gradient as an Eigen matrix.
        gtsam::Matrix gradientY() const;
        /// @return Validity mask represented as a zero/one Eigen matrix.
        gtsam::Matrix validMask() const;

        /// @return Patch width in pixels.
        int width() const;
        /// @return Patch height in pixels.
        int height() const;
        /// @return Patch center x coordinate in the source image.
        int centerX() const;
        /// @return Patch center y coordinate in the source image.
        int centerY() const;
        /// @return Absolute patch timestamp in microseconds.
        int64_t timestampUs() const;
        /// @return Fraction of patch pixels within sensor bounds.
        double validFraction() const;
        /// @return Mean squared spatial-gradient magnitude over valid pixels.
        double gradientEnergy() const;

      private:
        event_recon_fibar_core::SLocalFeaturePatch patch_;
    };

    /// @brief Adapts Eigen event arrays and images to the typed FIBAR core API.
    /// @details Owns the native reconstructor directly. gtwrap exposes only this
    ///          class's public conversion and orchestration methods. Native
    ///          filter ownership makes the adapter move-only.
    class CFibarReconstructorAdapter
    {
      public:
        /// @brief Construct an Eigen-facing convenience reconstructor.
        /// @param width Sensor width in pixels.
        /// @param height Sensor height in pixels.
        /// @param cutoff_time_us FIBAR temporal cutoff in microseconds.
        /// @param fill_ratio Spatial-filter fill ratio.
        /// @param use_spatial_filter Enable the upstream spatial filter.
        /// @throws std::invalid_argument If the native FIBAR configuration is
        ///         invalid.
        CFibarReconstructorAdapter(int width,
                                   int height,
                                   uint32_t cutoff_time_us,
                                   double fill_ratio,
                                   bool use_spatial_filter);

        /// @brief Clear all accepted events while preserving configuration.
        void reset();

        /// @brief Accept one signed-polarity event.
        /// @param x Sensor x coordinate.
        /// @param y Sensor y coordinate.
        /// @param polarity Signed event polarity.
        /// @param t_us Absolute timestamp in microseconds.
        /// @throws std::invalid_argument If the timestamp violates stream order.
        /// @throws std::out_of_range If the event lies outside the sensor.
        /// @throws std::runtime_error If the native relative timestamp overflows.
        void acceptEvent(uint16_t x, uint16_t y, int8_t polarity, int64_t t_us);

        /// @brief Validate and accept parallel Eigen event arrays.
        /// @param x Integral sensor x coordinates.
        /// @param y Integral sensor y coordinates.
        /// @param polarity Integral signed polarities.
        /// @param t_us Integral absolute timestamps in microseconds.
        /// @throws std::invalid_argument If array sizes, values, or timestamps are
        ///         invalid.
        /// @throws std::out_of_range If an event lies outside the sensor.
        /// @throws std::runtime_error If the native relative timestamp overflows.
        void acceptEvents(const gtsam::Vector &x,
                          const gtsam::Vector &y,
                          const gtsam::Vector &polarity,
                          const gtsam::Vector &t_us);

        /// @brief Copy the latest causal reconstruction into an Eigen matrix.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Owned image matrix.
        /// @throws std::runtime_error If no causal image exists.
        gtsam::Matrix requestImage(int64_t t_us) const;

        /// @brief Copy a local causal reconstruction patch for wrapper callers.
        /// @param center_x Patch center x coordinate.
        /// @param center_y Patch center y coordinate.
        /// @param radius Nonnegative patch radius.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Adapter-owned patch.
        /// @throws std::invalid_argument If the radius cannot form a valid patch.
        /// @throws std::runtime_error If no causal image exists.
        CLocalFeaturePatchAdapter requestPatch(int center_x,
                                               int center_y,
                                               int radius,
                                               int64_t t_us) const;

        /// @return Configured sensor width in pixels.
        int width() const;
        /// @return Configured sensor height in pixels.
        int height() const;
        /// @return Absolute timestamp of the latest accepted event, or `-1`.
        int64_t latestTimestampUs() const;

      private:
        event_recon_fibar_core::CFibarReconstructor reconstructor_;
    };

} // namespace wrap_adapters

#endif // WRAP_ADAPTERS_FIBAR_ADAPTERS_H_
