/// @file fibar_adapters.cpp
/// @brief Implements Eigen/native conversions for FIBAR convenience adapters.
/// @details All inputs are validated before they cross into the typed FIBAR
///          core so C++, Python, and MATLAB share one conversion policy.

#include "wrap_adapters/fibar_adapters.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace wrap_adapters
{
    namespace
    {

        template <typename TInteger>
        TInteger CheckedInteger(double value, const char *label)
        {
            static_assert(std::numeric_limits<TInteger>::is_integer &&
                              std::numeric_limits<TInteger>::radix == 2,
                          "FIBAR adapters require binary integer destination types");

            const double upper_bound =
                std::ldexp(1.0, std::numeric_limits<TInteger>::digits);
            const double lower_bound =
                std::numeric_limits<TInteger>::is_signed ? -upper_bound : 0.0;
            const double integral_value = std::trunc(value);
            if (!std::isfinite(value) ||
                integral_value < value || integral_value > value ||
                value < lower_bound || value >= upper_bound)
            {
                throw std::invalid_argument(std::string(label) +
                                            " values must be finite in-range integers");
            }
            return static_cast<TInteger>(value);
        }

        std::size_t CheckedPatchSize(int width, int height)
        {
            if (width == 0 && height == 0)
            {
                return 0;
            }
            if (width <= 0 || height <= 0)
            {
                throw std::invalid_argument(
                    "FIBAR patch dimensions must both be positive or both be zero");
            }

            const std::size_t width_value = static_cast<std::size_t>(width);
            const std::size_t height_value = static_cast<std::size_t>(height);
            if (height_value > std::numeric_limits<std::size_t>::max() / width_value)
            {
                throw std::invalid_argument("FIBAR patch dimensions overflow storage size");
            }
            return width_value * height_value;
        }

        void ValidatePatch(const event_recon_fibar_core::SLocalFeaturePatch &patch)
        {
            // Establish the geometry-derived storage contract before exposing any
            // matrix conversion.
            const std::size_t expected_size =
                CheckedPatchSize(patch.width, patch.height);
            if (patch.intensity.size() != expected_size ||
                patch.gradient_x.size() != expected_size ||
                patch.gradient_y.size() != expected_size ||
                patch.valid_mask.size() != expected_size)
            {
                throw std::invalid_argument(
                    "FIBAR patch arrays must match the declared geometry");
            }

            // Reject invalid quality metadata at the boundary so all language
            // consumers observe the same finite ranges.
            if (!std::isfinite(patch.valid_fraction) ||
                patch.valid_fraction < 0.0F || patch.valid_fraction > 1.0F)
            {
                throw std::invalid_argument(
                    "FIBAR patch valid fraction must be finite and within [0, 1]");
            }
            if (!std::isfinite(patch.gradient_energy) ||
                patch.gradient_energy < 0.0F)
            {
                throw std::invalid_argument(
                    "FIBAR patch gradient energy must be finite and nonnegative");
            }
        }

        /// @brief Map the convenience constructor arguments to the native contract.
        /// @return Validatable native FIBAR configuration.
        event_recon_fibar_core::SFibarConfig MakeCoreConfig(int width,
                                                           int height,
                                                           uint32_t cutoff_time_us,
                                                           double fill_ratio,
                                                           bool use_spatial_filter)
        {
            event_recon_fibar_core::SFibarConfig config;
            config.width = width;
            config.height = height;
            config.cutoff_time_us = cutoff_time_us;
            config.fill_ratio = fill_ratio;
            config.use_spatial_filter = use_spatial_filter;
            return config;
        }

        gtsam::Matrix ValuesToMatrix(const std::vector<float> &values, int width, int height)
        {
            gtsam::Matrix output(height, width);
            for (int row = 0; row < height; ++row)
            {
                const std::size_t row_offset =
                    static_cast<std::size_t>(row) * static_cast<std::size_t>(width);
                for (int column = 0; column < width; ++column)
                {
                    const std::size_t index =
                        row_offset + static_cast<std::size_t>(column);
                    output(row, column) = static_cast<double>(values.at(index));
                }
            }
            return output;
        }

    } // namespace

    CLocalFeaturePatchAdapter::CLocalFeaturePatchAdapter() = default;

    CLocalFeaturePatchAdapter::CLocalFeaturePatchAdapter(const event_recon_fibar_core::SLocalFeaturePatch &patch)
        : patch_(patch)
    {
        ValidatePatch(patch_);
    }

    std::size_t CLocalFeaturePatchAdapter::size() const
    {
        return patch_.intensity.size();
    }

    gtsam::Matrix CLocalFeaturePatchAdapter::intensity() const
    {
        return ValuesToMatrix(patch_.intensity, patch_.width, patch_.height);
    }

    gtsam::Matrix CLocalFeaturePatchAdapter::gradientX() const
    {
        return ValuesToMatrix(patch_.gradient_x, patch_.width, patch_.height);
    }

    gtsam::Matrix CLocalFeaturePatchAdapter::gradientY() const
    {
        return ValuesToMatrix(patch_.gradient_y, patch_.width, patch_.height);
    }

    gtsam::Matrix CLocalFeaturePatchAdapter::validMask() const
    {
        gtsam::Matrix output(patch_.height, patch_.width);
        for (int row = 0; row < patch_.height; ++row)
        {
            const std::size_t row_offset =
                static_cast<std::size_t>(row) *
                static_cast<std::size_t>(patch_.width);
            for (int column = 0; column < patch_.width; ++column)
            {
                const std::size_t index =
                    row_offset + static_cast<std::size_t>(column);
                output(row, column) = patch_.valid_mask.at(index) != 0U ? 1.0 : 0.0;
            }
        }
        return output;
    }

    int CLocalFeaturePatchAdapter::width() const
    {
        return patch_.width;
    }

    int CLocalFeaturePatchAdapter::height() const
    {
        return patch_.height;
    }

    int CLocalFeaturePatchAdapter::centerX() const
    {
        return patch_.center_x;
    }

    int CLocalFeaturePatchAdapter::centerY() const
    {
        return patch_.center_y;
    }

    int64_t CLocalFeaturePatchAdapter::timestampUs() const
    {
        return patch_.t_us;
    }

    double CLocalFeaturePatchAdapter::validFraction() const
    {
        return static_cast<double>(patch_.valid_fraction);
    }

    double CLocalFeaturePatchAdapter::gradientEnergy() const
    {
        return static_cast<double>(patch_.gradient_energy);
    }

    CFibarReconstructorAdapter::CFibarReconstructorAdapter(int width,
                                                           int height,
                                                           uint32_t cutoff_time_us,
                                                           double fill_ratio,
                                                           bool use_spatial_filter)
        : reconstructor_(MakeCoreConfig(width, height, cutoff_time_us,
                                        fill_ratio, use_spatial_filter))
    {
    }

    void CFibarReconstructorAdapter::reset()
    {
        reconstructor_.reset();
    }

    void CFibarReconstructorAdapter::acceptEvent(uint16_t x,
                                                 uint16_t y,
                                                 int8_t polarity,
                                                 int64_t t_us)
    {
        const event_recon_fibar_core::SEventBatchView batch{
            &x,
            &y,
            &polarity,
            &t_us,
            1,
            width(),
            height(),
        };
        reconstructor_.acceptEvents(batch);
    }

    void CFibarReconstructorAdapter::acceptEvents(const gtsam::Vector &x,
                                                  const gtsam::Vector &y,
                                                  const gtsam::Vector &polarity,
                                                  const gtsam::Vector &t_us)
    {
        if (y.size() != x.size() || polarity.size() != x.size() || t_us.size() != x.size())
        {
            throw std::invalid_argument("FIBAR event arrays must have equal lengths");
        }

        // Convert the complete batch before touching the native reconstructor so a
        // bad value cannot partially mutate its state.
        std::vector<uint16_t> x_values(static_cast<std::size_t>(x.size()));
        std::vector<uint16_t> y_values(static_cast<std::size_t>(y.size()));
        std::vector<int8_t> polarity_values(static_cast<std::size_t>(polarity.size()));
        std::vector<int64_t> timestamp_values(static_cast<std::size_t>(t_us.size()));
        for (Eigen::Index index = 0; index < x.size(); ++index)
        {
            const std::size_t output_index = static_cast<std::size_t>(index);
            x_values[output_index] = CheckedInteger<uint16_t>(x(index), "x");
            y_values[output_index] = CheckedInteger<uint16_t>(y(index), "y");
            polarity_values[output_index] = CheckedInteger<int8_t>(polarity(index), "polarity");
            timestamp_values[output_index] = CheckedInteger<int64_t>(t_us(index), "timestamp");
        }

        const event_recon_fibar_core::SEventBatchView batch{
            x_values.data(),
            y_values.data(),
            polarity_values.data(),
            timestamp_values.data(),
            x_values.size(),
            width(),
            height(),
        };
        reconstructor_.acceptEvents(batch);
    }

    gtsam::Matrix CFibarReconstructorAdapter::requestImage(int64_t t_us) const
    {
        const event_recon_fibar_core::SReconstructedImageView image =
            reconstructor_.requestImage(t_us);

        // Copy the non-owning row-major native image into caller-owned Eigen
        // storage before the native view can be invalidated.
        gtsam::Matrix output(image.height, image.width);
        for (int row = 0; row < image.height; ++row)
        {
            const std::size_t row_offset =
                static_cast<std::size_t>(row) *
                static_cast<std::size_t>(image.width);
            for (int column = 0; column < image.width; ++column)
            {
                const std::size_t index =
                    row_offset + static_cast<std::size_t>(column);
                output(row, column) = static_cast<double>(image.data[index]);
            }
        }
        return output;
    }

    CLocalFeaturePatchAdapter CFibarReconstructorAdapter::requestPatch(int center_x,
                                                                       int center_y,
                                                                       int radius,
                                                                       int64_t t_us) const
    {
        return CLocalFeaturePatchAdapter(reconstructor_.requestPatch(center_x,
                                                                     center_y,
                                                                     radius,
                                                                     t_us));
    }

    int CFibarReconstructorAdapter::width() const
    {
        return reconstructor_.width();
    }

    int CFibarReconstructorAdapter::height() const
    {
        return reconstructor_.height();
    }

    int64_t CFibarReconstructorAdapter::latestTimestampUs() const
    {
        return reconstructor_.latestTimestampUs();
    }

} // namespace wrap_adapters
