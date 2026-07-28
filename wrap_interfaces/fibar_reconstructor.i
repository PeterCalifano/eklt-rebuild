/// @file fibar_reconstructor.i
/// @brief Declares the generated-language surface of the FIBAR adapters.
/// @details Python and MATLAB share these declarations while conversion,
///          validation, and reconstruction remain in the native
///          `wrap_adapters` implementation.
namespace wrap_adapters
{

#include <wrap_adapters/GtsamAliases.h>
#include <wrap_adapters/fibar_adapters.h>

    /// @brief Exposes one adapter-owned reconstructed patch to generated code.
    class CLocalFeaturePatchAdapter
    {
        /// @brief Construct an empty patch value.
        CLocalFeaturePatchAdapter();

        /// @return Number of intensity samples in the patch.
        size_t size() const;
        /// @return Patch intensity as an owned matrix.
        gtsam::Matrix intensity() const;
        /// @return Horizontal patch gradient as an owned matrix.
        gtsam::Matrix gradientX() const;
        /// @return Vertical patch gradient as an owned matrix.
        gtsam::Matrix gradientY() const;
        /// @return Patch validity mask as an owned zero/one matrix.
        gtsam::Matrix validMask() const;

        /// @return Patch width in pixels.
        int width() const;
        /// @return Patch height in pixels.
        int height() const;
        /// @return Patch-center x coordinate in the source image.
        int centerX() const;
        /// @return Patch-center y coordinate in the source image.
        int centerY() const;
        /// @return Absolute patch timestamp in microseconds.
        int64_t timestampUs() const;
        /// @return Fraction of patch pixels inside the sensor bounds.
        double validFraction() const;
        /// @return Mean squared gradient magnitude over valid pixels.
        double gradientEnergy() const;
    };

    /// @brief Exposes validated Eigen-backed FIBAR reconstruction operations.
    class CFibarReconstructorAdapter
    {
        /// @brief Construct a wrapper-facing FIBAR reconstructor.
        /// @param width Sensor width in pixels.
        /// @param height Sensor height in pixels.
        /// @param cutoff_time_us Temporal cutoff in microseconds.
        /// @param fill_ratio Spatial-filter fill ratio.
        /// @param use_spatial_filter Enable spatial rather than temporal filtering.
        CFibarReconstructorAdapter(int width, int height, uint32_t cutoff_time_us,
                                   double fill_ratio, bool use_spatial_filter);

        /// @brief Clear accepted events while preserving configuration.
        void reset();

        /// @brief Accept one signed-polarity event.
        /// @param x Sensor x coordinate.
        /// @param y Sensor y coordinate.
        /// @param polarity Signed event polarity.
        /// @param t_us Absolute timestamp in microseconds.
        void acceptEvent(uint16_t x, uint16_t y, int8_t polarity, int64_t t_us);

        /// @brief Validate and atomically accept parallel event arrays.
        /// @param x Integral sensor x coordinates.
        /// @param y Integral sensor y coordinates.
        /// @param polarity Integral signed event polarities.
        /// @param t_us Integral absolute timestamps in microseconds.
        void acceptEvents(const gtsam::Vector &x, const gtsam::Vector &y,
                          const gtsam::Vector &polarity, const gtsam::Vector &t_us);

        /// @brief Request the latest causal reconstructed image.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Reconstructed image as an owned matrix.
        gtsam::Matrix requestImage(int64_t t_us) const;

        /// @brief Request one local causal reconstruction patch.
        /// @param center_x Patch-center x coordinate.
        /// @param center_y Patch-center y coordinate.
        /// @param radius Nonnegative patch radius.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Adapter-owned reconstructed patch.
        wrap_adapters::CLocalFeaturePatchAdapter requestPatch(int center_x, int center_y,
                                                              int radius, int64_t t_us) const;

        /// @return Configured sensor width in pixels.
        int width() const;
        /// @return Configured sensor height in pixels.
        int height() const;
        /// @return Latest accepted absolute timestamp, or `-1`.
        int64_t latestTimestampUs() const;
    };

} // namespace wrap_adapters
