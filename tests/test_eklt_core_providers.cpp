/// @file test_eklt_core_providers.cpp
/// @brief Verifies interchangeable frame, FIBAR, and future provider seams.
/// @details Exercises shared image validity, normalization, candidate and patch
///          contracts without introducing ROS or upstream FIBAR dependencies.

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

using Catch::Approx;

#include <cmath>
#include <limits>
#include <stdexcept>

#include <opencv2/imgproc.hpp>

#include "eklt_core/image_normalization.h"
#include "eklt_core/initialization_providers.h"

namespace
{

    /// @brief Construct a deterministic 8-bit frame with detectable corners.
    /// @return Valid timestamped image frame.
    eklt_core::SImageFrame MakeFrame()
    {
        cv::Mat image(32, 32, CV_8U, cv::Scalar(0));
        cv::rectangle(image, cv::Point(8, 8), cv::Point(24, 24), cv::Scalar(220), -1);
        cv::line(image, cv::Point(8, 8), cv::Point(24, 24), cv::Scalar(40), 2);

        eklt_core::SImageFrame frame;
        frame.image = image;
        frame.t_us = 100;
        frame.width = image.cols;
        frame.height = image.rows;
        return frame;
    }

    /// @brief Convert the deterministic frame into reconstructed-image-like storage.
    /// @return Valid `CV_32F` image frame with a non-unit source range.
    eklt_core::SImageFrame MakeFloatFrame()
    {
        const auto byte_frame = MakeFrame();
        cv::Mat image;
        byte_frame.image.convertTo(image, CV_32F, 0.03, -2.0);

        eklt_core::SImageFrame frame;
        frame.image = image;
        frame.t_us = byte_frame.t_us;
        frame.width = image.cols;
        frame.height = image.rows;
        return frame;
    }

} // namespace

TEST_CASE("Frame camera image provider returns latest causal frame", "[eklt_core]")
{
    // A retained frame becomes available exactly at its timestamp and remains
    // causal for subsequent requests.
    eklt_core::CFrameCameraImageProvider provider(MakeFrame());
    eklt_core::SImageFrame frame;

    CHECK_FALSE(provider.requestImage(99, eklt_core::EImageRequestReason::InitialBootstrap, &frame));
    REQUIRE(provider.requestImage(100, eklt_core::EImageRequestReason::InitialBootstrap, &frame));
    CHECK(frame.t_us == 100);
    CHECK(frame.width == 32);
    CHECK(frame.height == 32);
}

TEST_CASE("Frame Harris provider exposes current goodFeaturesToTrack path", "[eklt_core]")
{
    // Exercise the established OpenCV detector through the provider boundary
    // and retain its requested candidate limit and source timestamp.
    const auto frame = MakeFrame();
    eklt_core::SFrameHarrisConfig config;
    config.max_corners = 8;
    config.quality_level = 0.01;
    config.min_distance = 2.0;
    config.border = 2;
    eklt_core::CFrameHarrisCandidateProvider provider(config);
    std::vector<eklt_core::SFeatureCandidate> candidates;

    REQUIRE(provider.detectCandidates(frame, 8, &candidates));
    REQUIRE_FALSE(candidates.empty());
    CHECK(candidates.size() <= 8);
    CHECK(candidates.front().t_us == frame.t_us);
}

TEST_CASE("Frame patch provider returns local intensity and gradients", "[eklt_core]")
{
    // Request a centered patch so every output plane is backed by image data.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;

    REQUIRE(provider.requestPatch(candidate, 2, &patch));
    REQUIRE(patch.valid());
    CHECK(patch.intensity.rows == 5);
    CHECK(patch.intensity.cols == 5);
    CHECK(patch.valid_fraction == Approx(1.0));
    CHECK(patch.gradient_energy >= 0.0);
}

TEST_CASE("Frame patch provider rejects an overflowing radius", "[eklt_core]")
{
    // Radius validation must precede odd-size arithmetic and plane allocation.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;

    CHECK_FALSE(provider.requestPatch(candidate, std::numeric_limits<int>::max(), &patch));
}

TEST_CASE("Frame patch provider rejects a non-finite candidate center", "[eklt_core]")
{
    // Non-finite coordinates cannot be rounded safely into the integer image
    // domain used for extraction.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(std::numeric_limits<double>::infinity(), 16.0);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;

    CHECK_FALSE(provider.requestPatch(candidate, 2, &patch));
}

TEST_CASE("Frame patch provider rejects a candidate from another timestamp", "[eklt_core]")
{
    // A patch must retain the timestamp of its actual source image rather than
    // accepting candidate metadata from another initialization frame.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us + 1;
    eklt_core::SLocalFeaturePatch patch;

    CHECK_FALSE(provider.requestPatch(candidate, 2, &patch));
    CHECK(patch.intensity.empty());
}

TEST_CASE("Frame providers reject invalid detector and gradient configuration", "[eklt_core]")
{
    // Reject values that OpenCV cannot consume or that cannot participate in
    // safe exclusion-coordinate conversion.
    eklt_core::SFrameHarrisConfig harris_config;
    harris_config.quality_level = 0.0;
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.excluded_centers.push_back(cv::Point2d(std::numeric_limits<double>::infinity(), 0.0));
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.max_corners = 0;
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.min_distance = -1.0;
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.block_size = 0;
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.k = std::numeric_limits<double>::quiet_NaN();
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    harris_config = eklt_core::SFrameHarrisConfig();
    harris_config.border = -1;
    CHECK_THROWS_AS(eklt_core::CFrameHarrisCandidateProvider(harris_config),
                    std::invalid_argument);

    // Logarithmic gradients require a finite positive offset so the provider
    // never publishes NaN intensity derivatives.
    eklt_core::SFramePatchConfig patch_config;
    patch_config.log_eps = 0.0;
    CHECK_THROWS_AS(eklt_core::CFramePatchProvider(MakeFrame(), patch_config),
                    std::invalid_argument);

    patch_config.log_eps = std::numeric_limits<double>::infinity();
    CHECK_THROWS_AS(eklt_core::CFramePatchProvider(MakeFrame(), patch_config),
                    std::invalid_argument);
}

TEST_CASE("Frame providers accept reconstructed float images", "[eklt_core]")
{
    // Detect candidates directly from reconstructed-image-like floating-point
    // storage instead of assuming an 8-bit camera frame.
    const auto frame = MakeFloatFrame();
    eklt_core::SFrameHarrisConfig harris_config;
    harris_config.max_corners = 8;
    harris_config.quality_level = 0.01;
    harris_config.min_distance = 2.0;
    eklt_core::CFrameHarrisCandidateProvider candidate_provider(harris_config);
    std::vector<eklt_core::SFeatureCandidate> candidates;

    REQUIRE(candidate_provider.detectCandidates(frame, 8, &candidates));
    REQUIRE_FALSE(candidates.empty());

    // Reuse the same normalized frame representation for local patch
    // extraction and gradient-quality computation.
    eklt_core::CFramePatchProvider patch_provider(frame);
    eklt_core::SLocalFeaturePatch patch;
    REQUIRE(patch_provider.requestPatch(candidates.front(), 2, &patch));
    REQUIRE(patch.valid());
    CHECK(patch.valid_fraction > 0.0);
    CHECK(std::isfinite(patch.gradient_energy));
    CHECK(patch.gradient_energy >= 0.0);
    CHECK(patch.intensity.at<double>(2, 2) >= 0.0);
    CHECK(patch.intensity.at<double>(2, 2) <= 1.0);
}

TEST_CASE("Frame providers reject inconsistent image geometry", "[eklt_core]")
{
    // Break only the declared width so every provider sees the same invalid
    // frame contract while the underlying OpenCV storage remains intact.
    auto frame = MakeFrame();
    frame.width += 1;
    REQUIRE_FALSE(frame.valid());

    eklt_core::SImageFrame requested_frame;
    eklt_core::CFrameCameraImageProvider image_provider(frame);
    CHECK_FALSE(image_provider.requestImage(frame.t_us,
                                            eklt_core::EImageRequestReason::InitialBootstrap,
                                            &requested_frame));

    const eklt_core::SFrameHarrisConfig harris_config;
    eklt_core::CFrameHarrisCandidateProvider candidate_provider(harris_config);
    std::vector<eklt_core::SFeatureCandidate> candidates;
    CHECK_FALSE(candidate_provider.detectCandidates(frame, 4, &candidates));

    eklt_core::CFramePatchProvider patch_provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;
    CHECK_FALSE(patch_provider.requestPatch(candidate, 2, &patch));
}

TEST_CASE("Image normalization rejects non-2D storage", "[eklt_core]")
{
    // Multi-dimensional storage must not be mistaken for one scalar image.
    const int dimensions[] = {2, 3, 4};
    const cv::Mat volume(3, dimensions, CV_32F, cv::Scalar(1.0F));

    CHECK(eklt_core::NormalizeImageToUnitRange64(volume).empty());
    CHECK(eklt_core::NormalizeImageForGoodFeaturesToTrack(volume).empty());
}

TEST_CASE("Image normalization handles the complete finite double range", "[eklt_core]")
{
    // Exercise a source span that overflows direct double subtraction while
    // every individual sample remains finite.
    cv::Mat image(1, 3, CV_64F);
    image.at<double>(0, 0) = std::numeric_limits<double>::lowest();
    image.at<double>(0, 1) = 0.0;
    image.at<double>(0, 2) = std::numeric_limits<double>::max();

    const cv::Mat normalized = eklt_core::NormalizeImageToUnitRange64(image);

    REQUIRE(normalized.type() == CV_64F);
    REQUIRE(cv::checkRange(normalized));
    CHECK(normalized.at<double>(0, 0) == Approx(0.0));
    CHECK(normalized.at<double>(0, 1) == Approx(0.5));
    CHECK(normalized.at<double>(0, 2) == Approx(1.0));
}

TEST_CASE("Candidate plus patch initializer is provider agnostic", "[eklt_core]")
{
    // Adapt the frame patch implementation through the FIBAR-named callback
    // seam to prove the initializer depends only on the provider contract.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider frame_patch_provider(frame);
    const auto fibar_patch_callback =
        [&frame_patch_provider](const eklt_core::SFeatureCandidate &candidate,
                                int radius,
                                eklt_core::SLocalFeaturePatch *patch)
        {
            return frame_patch_provider.requestPatch(candidate, radius, patch);
        };
    eklt_core::CFibarPatchProvider fibar_patch_provider(fibar_patch_callback);

    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;
    eklt_core::SInitializedFeature feature;
    eklt_core::CFeatureInitializer initializer;

    REQUIRE(fibar_patch_provider.requestPatch(candidate, 2, &patch));
    REQUIRE(initializer.initialize(candidate, patch, &feature));
    CHECK(feature.candidate.center == candidate.center);
    CHECK(feature.patch.valid());
}

TEST_CASE("Candidate initializer rejects mismatched patch metadata", "[eklt_core]")
{
    // Preserve valid patch planes while invalidating only their timestamp
    // association with the candidate.
    const auto frame = MakeFrame();
    eklt_core::CFramePatchProvider patch_provider(frame);
    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;
    eklt_core::SLocalFeaturePatch patch;
    REQUIRE(patch_provider.requestPatch(candidate, 2, &patch));

    eklt_core::CFeatureInitializer initializer;
    eklt_core::SInitializedFeature feature;
    patch.t_us += 1;
    CHECK_FALSE(initializer.initialize(candidate, patch, &feature));
}

TEST_CASE("Future SuperEvent candidate provider only needs candidate interface", "[eklt_core]")
{
    /// @brief Minimal future-provider stand-in used to verify interface isolation.
    class CMockSuperEventCandidateProvider : public eklt_core::CFeatureCandidateProvider
    {
      public:
        bool detectCandidates(const eklt_core::SImageFrame &image,
                              int max_candidates,
                              std::vector<eklt_core::SFeatureCandidate> *candidates) override
        {
            if (candidates == nullptr || max_candidates <= 0)
            {
                return false;
            }
            candidates->clear();
            eklt_core::SFeatureCandidate candidate;
            candidate.center = cv::Point2d(image.width / 2, image.height / 2);
            candidate.response = 42.0;
            candidate.t_us = image.t_us;
            candidates->push_back(candidate);
            return true;
        }
    };

    // Compose the future candidate seam with the existing frame patch provider
    // and initializer without introducing a SuperEvent dependency.
    const auto frame = MakeFrame();
    CMockSuperEventCandidateProvider candidate_provider;
    eklt_core::CFramePatchProvider patch_provider(frame);
    std::vector<eklt_core::SFeatureCandidate> candidates;
    eklt_core::SLocalFeaturePatch patch;
    eklt_core::SInitializedFeature feature;
    eklt_core::CFeatureInitializer initializer;

    REQUIRE(candidate_provider.detectCandidates(frame, 4, &candidates));
    REQUIRE(patch_provider.requestPatch(candidates.front(), 2, &patch));
    REQUIRE(initializer.initialize(candidates.front(), patch, &feature));
    CHECK(feature.candidate.response == Approx(42.0));
}
