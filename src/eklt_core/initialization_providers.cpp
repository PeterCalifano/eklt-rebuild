/// @file initialization_providers.cpp
/// @brief Implements ROS-free feature initialization providers.
/// @details Keeps frame-backed and reconstructed-image provider behavior behind
///          the shared public contracts without introducing ROS dependencies.

#include "eklt_core/initialization_providers.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

#include <opencv2/imgproc/imgproc.hpp>

#include "eklt_core/image_normalization.h"

namespace eklt_core
{
    namespace
    {

        /// @brief Validate Harris detector and exclusion parameters once.
        /// @param config Configuration supplied to the candidate provider.
        /// @throws std::invalid_argument If a value cannot satisfy the detector
        ///         or coordinate-conversion contract.
        void ValidateHarrisConfig(const SFrameHarrisConfig &config)
        {
            if (config.max_corners <= 0)
            {
                throw std::invalid_argument("Harris max_corners must be positive");
            }
            if (!std::isfinite(config.quality_level) ||
                config.quality_level <= 0.0 || config.quality_level > 1.0)
            {
                throw std::invalid_argument("Harris quality_level must be finite and in (0, 1]");
            }
            if (!std::isfinite(config.min_distance) || config.min_distance < 0.0)
            {
                throw std::invalid_argument("Harris min_distance must be finite and nonnegative");
            }
            if (config.block_size <= 0)
            {
                throw std::invalid_argument("Harris block_size must be positive");
            }
            if (!std::isfinite(config.k))
            {
                throw std::invalid_argument("Harris k must be finite");
            }
            if (config.border < 0)
            {
                throw std::invalid_argument("Harris border must be nonnegative");
            }

            // Exclusion centers participate in floor/ceil and integer
            // conversion, so reject non-finite coordinates at construction.
            for (const cv::Point2d &center : config.excluded_centers)
            {
                if (!std::isfinite(center.x) || !std::isfinite(center.y))
                {
                    throw std::invalid_argument("Harris exclusion centers must be finite");
                }
            }
        }

        /// @brief Validate the logarithmic gradient offset.
        /// @param config Configuration supplied to the patch provider.
        /// @throws std::invalid_argument If the offset is non-finite or
        ///         nonpositive.
        void ValidateFramePatchConfig(const SFramePatchConfig &config)
        {
            if (!std::isfinite(config.log_eps) || config.log_eps <= 0.0)
            {
                throw std::invalid_argument("frame patch log_eps must be finite and positive");
            }
        }

    } // namespace

    bool SImageFrame::valid() const
    {
        // Bind the declared sensor geometry to one scalar OpenCV image so
        // providers cannot interpret stale or partial metadata differently.
        return !image.empty() && image.dims == 2 && image.channels() == 1 &&
               width > 0 && height > 0 && image.cols == width && image.rows == height;
    }

    bool SLocalFeaturePatch::valid() const
    {
        // Require all intensity, gradient, and validity planes to share the
        // representation consumed by the feature initializer.
        return !intensity.empty() && intensity.dims == 2 &&
               intensity.channels() == 1 && intensity.type() == CV_64F &&
               gradient_x.type() == CV_64F && gradient_y.type() == CV_64F &&
               valid_mask.type() == CV_8U &&
               intensity.size() == gradient_x.size() &&
               intensity.size() == gradient_y.size() &&
               intensity.size() == valid_mask.size();
    }

    CInitializationImageProvider::~CInitializationImageProvider() = default;
    CFeatureCandidateProvider::~CFeatureCandidateProvider() = default;
    CFeaturePatchProvider::~CFeaturePatchProvider() = default;

    CFrameCameraImageProvider::CFrameCameraImageProvider(const SImageFrame &frame)
        : frame_(frame)
    {
    }

    bool CFrameCameraImageProvider::requestImage(int64_t t_us,
                                                 EImageRequestReason reason,
                                                 SImageFrame *image)
    {
        static_cast<void>(reason);

        // Enforce the latest-causal request contract before exposing the
        // retained frame to the caller.
        if (image == nullptr || !frame_.valid() || frame_.t_us > t_us)
        {
            return false;
        }
        *image = frame_;
        return true;
    }

    CCallbackImageProvider::CCallbackImageProvider(TCallback callback)
        : callback_(callback)
    {
    }

    bool CCallbackImageProvider::requestImage(int64_t t_us,
                                              EImageRequestReason reason,
                                              SImageFrame *image)
    {
        return callback_ ? callback_(t_us, reason, image) : false;
    }

    CFrameHarrisCandidateProvider::CFrameHarrisCandidateProvider(const SFrameHarrisConfig &config)
        : config_(config)
    {
        ValidateHarrisConfig(config_);
    }

    bool CFrameHarrisCandidateProvider::detectCandidates(const SImageFrame &image,
                                                         int max_candidates,
                                                         std::vector<SFeatureCandidate> *candidates)
    {
        // Reject invalid output storage, image metadata, and request limits
        // before allocating detector state.
        if (candidates == nullptr || !image.valid() || max_candidates <= 0 ||
            config_.block_size > std::min(image.width, image.height))
        {
            return false;
        }

        // Build the candidate mask from the configured border and the
        // exclusion regions surrounding already active tracks.
        cv::Mat mask(image.height, image.width, CV_8U, cv::Scalar(255));
        if (config_.border > 0)
        {
            const int border = std::min(config_.border, std::min(image.width, image.height) / 2);
            mask.rowRange(0, border).setTo(0);
            mask.rowRange(image.height - border, image.height).setTo(0);
            mask.colRange(0, border).setTo(0);
            mask.colRange(image.width - border, image.width).setTo(0);
        }
        for (const cv::Point2d &center : config_.excluded_centers)
        {
            const double min_x_value = std::floor(center.x - config_.min_distance);
            const double max_x_value = std::ceil(center.x + config_.min_distance);
            const double min_y_value = std::floor(center.y - config_.min_distance);
            const double max_y_value = std::ceil(center.y + config_.min_distance);
            if (max_x_value < 0.0 || max_y_value < 0.0 ||
                min_x_value > image.width - 1 || min_y_value > image.height - 1)
            {
                continue;
            }

            // Clamp in floating point before converting so even very large
            // finite exclusion ranges remain representable.
            const int min_x = static_cast<int>(std::max(0.0, min_x_value));
            const int max_x =
                static_cast<int>(std::min(static_cast<double>(image.width - 1), max_x_value));
            const int min_y = static_cast<int>(std::max(0.0, min_y_value));
            const int max_y =
                static_cast<int>(std::min(static_cast<double>(image.height - 1), max_y_value));
            mask.rowRange(min_y, max_y + 1).colRange(min_x, max_x + 1).setTo(0);
        }

        // Convert reconstructed floating-point images through the same finite
        // normalization path used by frame-backed initialization.
        const cv::Mat detection_image = NormalizeImageForGoodFeaturesToTrack(image.image);
        if (detection_image.empty())
        {
            return false;
        }

        // Run the existing Harris-backed OpenCV detector within the caller's
        // limit and the provider's configured upper bound.
        std::vector<cv::Point2f> corners;
        cv::goodFeaturesToTrack(detection_image, corners,
                                std::min(max_candidates, config_.max_corners),
                                config_.quality_level, config_.min_distance,
                                mask, config_.block_size, true, config_.k);

        // Translate OpenCV corners into timestamped provider-independent
        // candidates while preserving detector priority.
        candidates->clear();
        candidates->reserve(corners.size());
        for (std::size_t i = 0; i < corners.size(); ++i)
        {
            SFeatureCandidate candidate;
            candidate.center = corners[i];
            candidate.response = 1.0;
            candidate.scale = 1.0;
            candidate.t_us = image.t_us;
            candidate.id = static_cast<int>(i);
            candidates->push_back(candidate);
        }
        return true;
    }

    CFramePatchProvider::CFramePatchProvider(const SImageFrame &frame,
                                             const SFramePatchConfig &config)
        : frame_(frame), config_(config)
    {
        ValidateFramePatchConfig(config_);

        // Cache normalized intensity and gradients once because every requested
        // patch shares the same immutable source frame.
        if (frame_.valid())
        {
            normalized_intensity_ = NormalizeImageToUnitRange64(frame_.image);
            computeGradients(normalized_intensity_, config_.log_eps, gradient_x_, gradient_y_);
        }
    }

    bool CFramePatchProvider::requestPatch(const SFeatureCandidate &candidate,
                                           int radius,
                                           SLocalFeaturePatch *patch)
    {
        // Validate all caller-controlled inputs before performing geometry
        // arithmetic or allocating patch planes.
        if (patch == nullptr || !frame_.valid() || radius < 0 ||
            radius > (std::numeric_limits<int>::max() - 1) / 2 ||
            candidate.t_us != frame_.t_us ||
            !std::isfinite(candidate.center.x) ||
            !std::isfinite(candidate.center.y) ||
            normalized_intensity_.empty() || gradient_x_.empty() || gradient_y_.empty())
        {
            return false;
        }

        // Form a representable odd patch geometry and reject candidate
        // coordinates that cannot be rounded into the integer image domain.
        const int size = 2 * radius + 1;
        const double rounded_center_x = std::round(candidate.center.x);
        const double rounded_center_y = std::round(candidate.center.y);
        if (rounded_center_x < std::numeric_limits<int>::min() ||
            rounded_center_x > std::numeric_limits<int>::max() ||
            rounded_center_y < std::numeric_limits<int>::min() ||
            rounded_center_y > std::numeric_limits<int>::max())
        {
            return false;
        }

        // Allocate zero-filled planes so samples outside the source image
        // retain deterministic intensity, gradient, and validity values.
        cv::Mat intensity(size, size, CV_64F, cv::Scalar(0));
        cv::Mat gradient_x(size, size, CV_64F, cv::Scalar(0));
        cv::Mat gradient_y(size, size, CV_64F, cv::Scalar(0));
        cv::Mat valid_mask(size, size, CV_8U, cv::Scalar(0));

        const int center_x = static_cast<int>(rounded_center_x);
        const int center_y = static_cast<int>(rounded_center_y);
        std::size_t valid_count = 0;
        double gradient_energy = 0.0;

        // Copy in-bounds samples and accumulate the gradient-quality metric
        // without converting out-of-bounds coordinates to narrow integers.
        for (int py = 0; py < size; ++py)
        {
            const int64_t y = static_cast<int64_t>(center_y) + py - radius;
            for (int px = 0; px < size; ++px)
            {
                const int64_t x = static_cast<int64_t>(center_x) + px - radius;
                if (x < 0 || y < 0 || x >= frame_.width || y >= frame_.height)
                {
                    continue;
                }
                const int valid_x = static_cast<int>(x);
                const int valid_y = static_cast<int>(y);
                valid_mask.at<uint8_t>(py, px) = 1U;
                intensity.at<double>(py, px) = normalized_intensity_.at<double>(valid_y, valid_x);
                const double gx = gradient_x_.at<double>(valid_y, valid_x);
                const double gy = gradient_y_.at<double>(valid_y, valid_x);
                gradient_x.at<double>(py, px) = gx;
                gradient_y.at<double>(py, px) = gy;
                gradient_energy += gx * gx + gy * gy;
                ++valid_count;
            }
        }

        // Publish the complete patch atomically after all planes and quality
        // statistics have been derived successfully.
        patch->intensity = intensity;
        patch->gradient_x = gradient_x;
        patch->gradient_y = gradient_y;
        patch->valid_mask = valid_mask;
        patch->center = candidate.center;
        patch->t_us = frame_.t_us;
        patch->valid_fraction = static_cast<double>(valid_count) /
                                (static_cast<double>(size) * static_cast<double>(size));
        patch->gradient_energy = valid_count > 0 ? gradient_energy / static_cast<double>(valid_count) : 0.0;
        return true;
    }

    void CFramePatchProvider::computeGradients(const cv::Mat &normalized_image,
                                               double log_eps,
                                               cv::Mat &gradient_x,
                                               cv::Mat &gradient_y)
    {
        // Derive log-intensity Sobel gradients in double precision so frame and
        // reconstructed-image providers expose the same patch contract.
        cv::Mat log_image;
        if (normalized_image.empty())
        {
            return;
        }
        cv::log(normalized_image + std::max(log_eps, std::numeric_limits<double>::epsilon()), log_image);
        cv::Sobel(log_image / 8.0, gradient_x, CV_64F, 1, 0, 3);
        cv::Sobel(log_image / 8.0, gradient_y, CV_64F, 0, 1, 3);
    }

    CCallbackPatchProvider::CCallbackPatchProvider(TCallback callback)
        : callback_(callback)
    {
    }

    bool CCallbackPatchProvider::requestPatch(const SFeatureCandidate &candidate,
                                              int radius,
                                              SLocalFeaturePatch *patch)
    {
        return callback_ ? callback_(candidate, radius, patch) : false;
    }

    CFibarImageProvider::CFibarImageProvider(TCallback callback)
        : CCallbackImageProvider(callback)
    {
    }

    CFibarHarrisCandidateProvider::CFibarHarrisCandidateProvider(const SFrameHarrisConfig &config)
        : CFrameHarrisCandidateProvider(config)
    {
    }

    CFibarPatchProvider::CFibarPatchProvider(TCallback callback)
        : CCallbackPatchProvider(callback)
    {
    }

    bool CFeatureInitializer::initialize(const SFeatureCandidate &candidate,
                                         const SLocalFeaturePatch &patch,
                                         SInitializedFeature *feature) const
    {
        // Require patch geometry, quality, timestamp, and center metadata to
        // describe the exact candidate being initialized.
        if (feature == nullptr || !patch.valid() ||
            !std::isfinite(patch.valid_fraction) ||
            patch.valid_fraction <= 0.0 || patch.valid_fraction > 1.0 ||
            !std::isfinite(patch.gradient_energy) ||
            patch.t_us != candidate.t_us || patch.center != candidate.center)
        {
            return false;
        }

        // Copy the compatible provider outputs together only after the complete
        // initialization contract has passed.
        feature->candidate = candidate;
        feature->patch = patch;
        return true;
    }

} // namespace eklt_core
