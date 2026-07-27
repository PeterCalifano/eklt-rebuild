/// @file image_normalization.h
/// @brief Provides shared C++17 normalization for frame and FIBAR images.
/// @details Internal normalization remains separate from display conversion
///          and maps non-finite floating-point samples to zero.

#ifndef EKLT_CORE_IMAGE_NORMALIZATION_H_
#define EKLT_CORE_IMAGE_NORMALIZATION_H_

#include <opencv2/core/core.hpp>

namespace eklt_core
{

    /// @brief Convert a single-channel image to finite `CV_64F` values in `[0, 1]`.
    /// @param image Source image. Eight-bit input keeps its fixed 255 scale; other
    ///              depths are min-max normalized over finite samples.
    /// @return Normalized image, or an empty matrix for invalid shape/channel input.
    /// @details Finite ranges that overflow during direct subtraction are scaled
    ///          before normalization.
    cv::Mat NormalizeImageToUnitRange64(const cv::Mat &image);

    /// @brief Convert an image to an OpenCV corner-detector-compatible type.
    /// @param image Single-channel source image.
    /// @return Original `CV_8U` data or normalized `CV_32F` data.
    cv::Mat NormalizeImageForGoodFeaturesToTrack(const cv::Mat &image);

} // namespace eklt_core

#endif // EKLT_CORE_IMAGE_NORMALIZATION_H_
