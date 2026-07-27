/// @file image_normalization.cpp
/// @brief Implements finite normalization for frame and FIBAR images.
/// @details Keeps numeric-range handling behind the shared C++17 declarations
///          used by frame-backed and reconstructed-image paths.

#include "eklt_core/image_normalization.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace eklt_core
{

    cv::Mat NormalizeImageToUnitRange64(const cv::Mat &image)
    {
        // Reject storage that cannot be interpreted as one scalar image.
        if (image.empty() || image.dims != 2 || image.channels() != 1)
        {
            return cv::Mat();
        }

        // Preserve the conventional fixed 8-bit intensity scale instead of
        // stretching each frame independently.
        if (image.depth() == CV_8U)
        {
            cv::Mat normalized;
            image.convertTo(normalized, CV_64F, 1.0 / 255.0);
            return normalized;
        }

        // Convert once to double precision and derive the finite source range
        // without allowing invalid samples to influence it.
        cv::Mat values;
        image.convertTo(values, CV_64F);

        double min_value = std::numeric_limits<double>::infinity();
        double max_value = -std::numeric_limits<double>::infinity();
        for (int row = 0; row < values.rows; ++row)
        {
            const double *row_ptr = values.ptr<double>(row);
            for (int col = 0; col < values.cols; ++col)
            {
                const double value = row_ptr[col];
                if (!std::isfinite(value))
                {
                    continue;
                }
                min_value = std::min(min_value, value);
                max_value = std::max(max_value, value);
            }
        }

        // Represent images without a usable finite range as a deterministic
        // zero image of the expected type and geometry.
        cv::Mat normalized = cv::Mat::zeros(values.size(), CV_64F);
        if (!std::isfinite(min_value) || !std::isfinite(max_value))
        {
            return normalized;
        }

        const double span = max_value - min_value;
        if (span <= std::numeric_limits<double>::epsilon())
        {
            return normalized;
        }

        // Scale extreme finite ranges before subtraction so their span remains
        // representable without changing ordinary-range normalization.
        const bool span_is_finite = std::isfinite(span);
        const double scale = span_is_finite
                                 ? 1.0
                                 : std::max(std::abs(min_value), std::abs(max_value));
        const double scaled_min = min_value / scale;
        const double scaled_span = span_is_finite
                                       ? span
                                       : max_value / scale - scaled_min;

        // Map every finite sample into the unit interval and replace invalid
        // samples with zero so downstream OpenCV operations remain finite.
        for (int row = 0; row < values.rows; ++row)
        {
            const double *src = values.ptr<double>(row);
            double *dst = normalized.ptr<double>(row);
            for (int col = 0; col < values.cols; ++col)
            {
                const double value = src[col];
                if (!std::isfinite(value))
                {
                    dst[col] = 0.0;
                    continue;
                }
                const double normalized_value = span_is_finite
                                                    ? (value - min_value) / scaled_span
                                                    : (value / scale - scaled_min) / scaled_span;
                dst[col] = std::max(0.0, std::min(1.0, normalized_value));
            }
        }
        return normalized;
    }

    cv::Mat NormalizeImageForGoodFeaturesToTrack(const cv::Mat &image)
    {
        // Apply the same scalar-image contract as the core normalization path.
        if (image.empty() || image.dims != 2 || image.channels() != 1)
        {
            return cv::Mat();
        }

        // goodFeaturesToTrack natively accepts 8-bit images, so keep that
        // representation unchanged and normalize only other depths.
        if (image.depth() == CV_8U)
        {
            return image;
        }

        const cv::Mat normalized64 = NormalizeImageToUnitRange64(image);
        cv::Mat normalized32;
        normalized64.convertTo(normalized32, CV_32F);
        return normalized32;
    }

} // namespace eklt_core
