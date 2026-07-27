/// @file fibar_reconstructor.cpp
/// @brief Implements the ROS-free facade over the upstream FIBAR reconstructor.
/// @details Owns timestamp normalization, input validation, image snapshots,
///          local patch extraction, and display-only normalization.

#include "event_recon_fibar_core/fibar_reconstructor.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

#include <fibar_lib/image_reconstructor.hpp>

namespace event_recon_fibar_core
{
    namespace
    {

        /// @brief Validate the fixed sensor and filter configuration.
        /// @param config Configuration supplied to the reconstructor.
        /// @throws std::invalid_argument If a configuration value violates the
        ///         FIBAR facade contract.
        void ValidateConfig(const SFibarConfig &config)
        {
            if (config.width <= 0 || config.height <= 0)
            {
                throw std::invalid_argument("FIBAR width and height must be positive");
            }
            if (config.cutoff_time_us == 0)
            {
                throw std::invalid_argument("FIBAR cutoff_time_us must be positive");
            }
            if (!(config.fill_ratio > 0.0 && config.fill_ratio <= 1.0))
            {
                throw std::invalid_argument("FIBAR fill_ratio must be in (0, 1]");
            }
        }

        /// @brief Read one in-bounds row-major pixel or return the zero border.
        /// @param image Contiguous source image.
        /// @param width Source width in pixels.
        /// @param height Source height in pixels.
        /// @param x Requested x coordinate.
        /// @param y Requested y coordinate.
        /// @return Source value for an in-bounds coordinate, otherwise zero.
        double PixelOrZero(const std::vector<float> &image, int width, int height, int x, int y)
        {
            if (x < 0 || y < 0 || x >= width || y >= height)
            {
                return 0.0;
            }
            return image[static_cast<std::size_t>(y) * static_cast<std::size_t>(width) +
                         static_cast<std::size_t>(x)];
        }

    } // namespace

    std::vector<uint8_t> NormalizeImageForDisplay(const float *image, std::size_t image_size)
    {
        // Validate the non-owning input before allocating or traversing output
        // storage.
        if (image == nullptr && image_size != 0)
        {
            throw std::invalid_argument("display normalization input is null");
        }

        std::vector<uint8_t> output(image_size, 0);
        if (image_size == 0)
        {
            return output;
        }

        // Derive the complete finite display range and fail explicitly when the
        // upstream reconstruction contains an invalid value.
        float min_value = std::numeric_limits<float>::infinity();
        float max_value = -std::numeric_limits<float>::infinity();
        for (std::size_t i = 0; i < image_size; ++i)
        {
            if (!std::isfinite(image[i]))
            {
                throw std::runtime_error("display normalization input contains non-finite values");
            }
            min_value = std::min(min_value, image[i]);
            max_value = std::max(max_value, image[i]);
        }

        // Widen before subtraction so the complete finite float range has a
        // representable normalization span.
        const double min_value_double = static_cast<double>(min_value);
        const double span = static_cast<double>(max_value) - min_value_double;
        if (span <= static_cast<double>(std::numeric_limits<float>::epsilon()))
        {
            return output;
        }

        // Convert only the display copy to 8-bit storage, leaving the facade's
        // owned float reconstruction unchanged.
        for (std::size_t i = 0; i < image_size; ++i)
        {
            const double normalized = (static_cast<double>(image[i]) - min_value_double) / span;
            output[i] = static_cast<uint8_t>(std::round(std::max(0.0, std::min(1.0, normalized)) * 255.0));
        }
        return output;
    }

    CFibarReconstructor::CFibarReconstructor(const SFibarConfig &config) : config_(config)
    {
        initialize();
    }

    CFibarReconstructor::~CFibarReconstructor() = default;

    CFibarReconstructor::CFibarReconstructor(CFibarReconstructor &&other) noexcept = default;

    CFibarReconstructor &CFibarReconstructor::operator=(CFibarReconstructor &&other) noexcept = default;

    void CFibarReconstructor::initialize()
    {
        // Revalidate immutable configuration on construction and reset so
        // both paths establish the same initial state.
        ValidateConfig(config_);
        latest_t_us_ = -1;
        time_origin_us_ = -1;

        // Prove the row-major image size is representable before allocating
        // facade-owned storage or configuring the upstream implementation.
        if (static_cast<std::size_t>(config_.width) >
            std::numeric_limits<std::size_t>::max() /
                static_cast<std::size_t>(config_.height))
        {
            throw std::invalid_argument("FIBAR sensor geometry exceeds addressable image storage");
        }
        const std::size_t image_size = static_cast<std::size_t>(config_.width) *
                                       static_cast<std::size_t>(config_.height);
        image_.assign(image_size, 0.0F);

        // Instantiate exactly one upstream reconstruction mode while
        // retaining one stable EKLT facade and output representation.
        if (config_.use_spatial_filter)
        {
            spatial_ = std::make_unique<TSpatialReconstructor>();
            spatial_->initialize(static_cast<std::size_t>(config_.width),
                                 static_cast<std::size_t>(config_.height),
                                 config_.cutoff_time_us, config_.fill_ratio);
            temporal_.reset();
        }
        else
        {
            temporal_ = std::make_unique<TTemporalReconstructor>();
            temporal_->initialize(static_cast<std::size_t>(config_.width),
                                  static_cast<std::size_t>(config_.height),
                                  config_.cutoff_time_us);
            spatial_.reset();
        }
    }

    void CFibarReconstructor::reset()
    {
        initialize();
    }

    void CFibarReconstructor::acceptEvents(const SEventBatchView &events)
    {
        // Validate the complete batch before mutating the upstream state so
        // rejected input cannot be applied partially.
        validateBatch(events);

        // Anchor the upstream relative clock to the first accepted event
        // while preserving absolute timestamps at the public boundary.
        if (events.size != 0 && time_origin_us_ < 0)
        {
            time_origin_us_ = events.t_us[0];
        }

        // Translate absolute signed-polarity events into the upstream
        // relative uint32 clock and binary polarity representation.
        for (std::size_t i = 0; i < events.size; ++i)
        {
            const uint16_t x = events.x[i];
            const uint16_t y = events.y[i];
            const int64_t relative_t_us = events.t_us[i] - time_origin_us_;
            const uint8_t polarity = events.p[i] > 0 ? 1U : 0U;
            const uint32_t t = static_cast<uint32_t>(relative_t_us);
            if (spatial_)
            {
                spatial_->event(t, x, y, polarity);
            }
            else
            {
                temporal_->event(t, x, y, polarity);
            }
            latest_t_us_ = events.t_us[i];
        }

        // Snapshot the upstream state after the complete accepted batch so
        // facade views and copies observe one coherent image.
        refreshImage();
    }

    bool CFibarReconstructor::hasImageFor(int64_t t_us) const
    {
        return latest_t_us_ >= 0 && latest_t_us_ <= t_us;
    }

    SReconstructedImageView CFibarReconstructor::requestImage(int64_t t_us) const
    {
        // Serve only the latest state that is causal for the requested
        // absolute timestamp.
        if (!hasImageFor(t_us))
        {
            throw std::runtime_error("no latest-causal FIBAR image is available for requested timestamp");
        }
        refreshImage();
        return SReconstructedImageView{
            image_.data(),
            image_.size(),
            config_.width,
            config_.height,
            latest_t_us_,
        };
    }

    void CFibarReconstructor::copyImageTo(float *output, std::size_t output_size) const
    {
        // Require the caller-owned buffer to represent the complete image;
        // partial copies would violate the fixed-geometry facade contract.
        if (output == nullptr && output_size != 0)
        {
            throw std::invalid_argument("copyImageTo output is null");
        }
        if (output_size != image_.size())
        {
            throw std::invalid_argument("copyImageTo output size does not match image size");
        }
        std::copy(image_.begin(), image_.end(), output);
    }

    std::vector<uint8_t> CFibarReconstructor::makeDisplayImage(int64_t t_us) const
    {
        const SReconstructedImageView image = requestImage(t_us);
        return NormalizeImageForDisplay(image.data, image.size);
    }

    SLocalFeaturePatch CFibarReconstructor::requestPatch(int center_x, int center_y, int radius, int64_t t_us) const
    {
        const SReconstructedImageView view = requestImage(t_us);

        // Reject radius arithmetic that cannot produce a positive odd patch
        // width in the public integer representation.
        if (radius < 0 ||
            radius > (std::numeric_limits<int>::max() - 1) / 2)
        {
            throw std::invalid_argument("patch radius must be nonnegative and produce a "
                                        "representable odd size");
        }

        // Validate the odd patch width before using it for allocation or
        // coordinate arithmetic.
        const int patch_size = 2 * radius + 1;
        const std::size_t patch_side = static_cast<std::size_t>(patch_size);
        if (patch_side >
            std::numeric_limits<std::size_t>::max() / patch_side)
        {
            throw std::invalid_argument("patch geometry exceeds addressable storage");
        }

        // Allocate every returned plane from the same checked geometry and
        // initialize the out-of-sensor border deterministically.
        SLocalFeaturePatch patch;
        patch.width = patch_size;
        patch.height = patch_size;
        patch.center_x = center_x;
        patch.center_y = center_y;
        patch.t_us = view.t_us;
        const std::size_t size = patch_side * patch_side;
        patch.intensity.assign(size, 0.0F);
        patch.gradient_x.assign(size, 0.0F);
        patch.gradient_y.assign(size, 0.0F);
        patch.valid_mask.assign(size, 0U);

        std::size_t valid_count = 0;
        double gradient_energy_sum = 0.0;

        // Extract all in-bounds intensity samples and central-difference
        // gradients while retaining an explicit zero-valued invalid border.
        for (int py = 0; py < patch_size; ++py)
        {
            const int64_t y = static_cast<int64_t>(center_y) + py - radius;
            for (int px = 0; px < patch_size; ++px)
            {
                const int64_t x = static_cast<int64_t>(center_x) + px - radius;
                const std::size_t index =
                    static_cast<std::size_t>(py) * patch_side +
                    static_cast<std::size_t>(px);
                if (x < 0 || y < 0 || x >= config_.width || y >= config_.height)
                {
                    continue;
                }

                const int valid_x = static_cast<int>(x);
                const int valid_y = static_cast<int>(y);
                patch.valid_mask[index] = 1U;
                ++valid_count;
                patch.intensity[index] =
                    image_[static_cast<std::size_t>(valid_y) *
                               static_cast<std::size_t>(config_.width) +
                           static_cast<std::size_t>(valid_x)];

                const double gx =
                    0.5 * (PixelOrZero(image_, config_.width, config_.height, valid_x + 1, valid_y) -
                           PixelOrZero(image_, config_.width, config_.height, valid_x - 1, valid_y));
                const double gy =
                    0.5 * (PixelOrZero(image_, config_.width, config_.height, valid_x, valid_y + 1) -
                           PixelOrZero(image_, config_.width, config_.height, valid_x, valid_y - 1));
                patch.gradient_x[index] = static_cast<float>(gx);
                patch.gradient_y[index] = static_cast<float>(gy);
                gradient_energy_sum += gx * gx + gy * gy;
            }
        }

        // Derive coverage and gradient quality only from valid sensor
        // samples after the complete patch has been populated.
        patch.valid_fraction = static_cast<float>(valid_count) / static_cast<float>(size);
        patch.gradient_energy =
            valid_count > 0 ? static_cast<float>(gradient_energy_sum / static_cast<double>(valid_count)) : 0.0F;
        return patch;
    }

    int CFibarReconstructor::width() const
    {
        return config_.width;
    }

    int CFibarReconstructor::height() const
    {
        return config_.height;
    }

    int64_t CFibarReconstructor::latestTimestampUs() const
    {
        return latest_t_us_;
    }

    void CFibarReconstructor::validateBatch(const SEventBatchView &events) const
    {
        // Empty batches carry no array or geometry requirements and preserve
        // the current reconstruction state.
        if (events.size == 0)
        {
            return;
        }

        // Require a complete structure-of-arrays view and accept optional
        // geometry only when it matches the configured sensor.
        if (events.x == nullptr || events.y == nullptr || events.p == nullptr || events.t_us == nullptr)
        {
            throw std::invalid_argument("FIBAR event batch has null array pointer");
        }
        if (events.width != 0 && events.width != config_.width)
        {
            throw std::invalid_argument("FIBAR event batch width does not match config");
        }
        if (events.height != 0 && events.height != config_.height)
        {
            throw std::invalid_argument("FIBAR event batch height does not match config");
        }

        // Establish cross-batch timestamp causality before inspecting the
        // remaining events in this batch.
        if (events.t_us[0] < 0)
        {
            throw std::invalid_argument("FIBAR event timestamps must be nonnegative");
        }
        if (latest_t_us_ >= 0 && events.t_us[0] < latest_t_us_)
        {
            throw std::invalid_argument("FIBAR event batches must be monotonically nondecreasing");
        }
        const int64_t time_origin_us = time_origin_us_ >= 0 ? time_origin_us_ : events.t_us[0];

        // Validate every event before acceptEvents forwards any sample to
        // the upstream reconstructor.
        for (std::size_t i = 0; i < events.size; ++i)
        {
            if (i > 0 && events.t_us[i] < events.t_us[i - 1])
            {
                throw std::invalid_argument("FIBAR event batch timestamps must be monotonically nondecreasing");
            }
            if (static_cast<int>(events.x[i]) >= config_.width ||
                static_cast<int>(events.y[i]) >= config_.height)
            {
                throw std::out_of_range("FIBAR event coordinate outside configured sensor bounds");
            }
            if (events.t_us[i] - time_origin_us >
                static_cast<int64_t>(std::numeric_limits<uint32_t>::max()))
            {
                throw std::runtime_error("FIBAR relative timestamp exceeds uint32 microsecond range");
            }
        }
    }

    void CFibarReconstructor::refreshImage() const
    {
        // Read state from the single configured upstream mode into the
        // facade-owned contiguous image.
        if (spatial_)
        {
            copyState(spatial_->getState());
        }
        else
        {
            copyState(temporal_->getState());
        }
    }

    template <typename TStateVector>
    void CFibarReconstructor::copyState(const TStateVector &state) const
    {
        // Enforce geometry and finiteness before exposing the refreshed
        // reconstruction through any public view.
        if (state.size() != image_.size())
        {
            throw std::runtime_error("FIBAR state size does not match configured image size");
        }
        for (std::size_t i = 0; i < state.size(); ++i)
        {
            const float value = state[i].getL();
            if (!std::isfinite(value))
            {
                throw std::runtime_error("FIBAR produced non-finite image value");
            }
            image_[i] = value;
        }
    }

} // namespace event_recon_fibar_core
