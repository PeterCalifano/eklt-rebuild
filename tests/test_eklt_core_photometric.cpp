/// @file test_eklt_core_photometric.cpp
/// @brief Verifies deterministic event frames and finite Ceres patch updates.
/// @details Covers bounded accumulation, geometry rejection, flow bootstrap,
///          and solver-state validity through the public ROS-free API.

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <stdexcept>

#include <opencv2/imgproc.hpp>

#include "eklt_core/initialization_providers.h"
#include "eklt_core/photometric_patch_tracker.h"

namespace
{

    /// @brief Construct one deterministic tracker event.
    /// @param x Sensor x coordinate.
    /// @param y Sensor y coordinate.
    /// @param p Signed polarity.
    /// @param t_us Absolute timestamp in microseconds.
    /// @return Populated event sample.
    eklt_core::SEventSample MakeEvent(uint16_t x, uint16_t y, int8_t p, int64_t t_us)
    {
        eklt_core::SEventSample event;
        event.x = x;
        event.y = y;
        event.p = p;
        event.t_us = t_us;
        return event;
    }

    /// @brief Construct a float image with a repeatable central corner.
    /// @return Single-channel `CV_32F` corner image.
    cv::Mat MakeCornerImage()
    {
        cv::Mat image(32, 32, CV_32F, cv::Scalar(0.0F));
        cv::line(image, cv::Point(8, 16), cv::Point(24, 16), cv::Scalar(1.0F), 2);
        cv::line(image, cv::Point(16, 8), cv::Point(16, 24), cv::Scalar(1.0F), 2);
        return image;
    }

} // namespace

TEST_CASE("Photometric patch builds deterministic event frame", "[eklt_core]")
{
    // Fill one bounded patch window with a deterministic signed event pattern.
    eklt_core::SPhotometricPatch patch(7, cv::Point2d(10, 10), 1000, 5, 4, 2);
    patch.insert(MakeEvent(10, 10, 1, 1000));
    patch.insert(MakeEvent(11, 10, -1, 1100));
    patch.insert(MakeEvent(10, 11, 1, 1200));
    patch.insert(MakeEvent(11, 11, -1, 1300));

    // Accumulation must produce one finite update and reset only the new-event
    // counter while retaining the configured patch geometry.
    REQUIRE(patch.readyForUpdate());
    cv::Mat event_frame;
    REQUIRE(patch.getEventFrameAndReset(&event_frame));

    REQUIRE(event_frame.rows == 5);
    REQUIRE(event_frame.cols == 5);
    CHECK(patch.t_curr_us == 1150);
    CHECK(cv::norm(event_frame) > 0.0);
    CHECK(patch.event_counter == 0);
}

TEST_CASE("Photometric patch rejects non-odd geometry", "[eklt_core]")
{
    // Reject ambiguous even-sized patch geometry at construction rather than
    // allowing later accumulation to select an implicit center.
    CHECK_THROWS_AS(eklt_core::SPhotometricPatch(7, cv::Point2d(10, 10), 1000, 4, 4, 2),
                    std::invalid_argument);
}

TEST_CASE("Photometric optimizer updates finite patch state", "[eklt_core]")
{
    // Build the initialization patch and transfer its gradients into the
    // asynchronous photometric state.
    const cv::Mat image = MakeCornerImage();
    eklt_core::SImageFrame frame;
    frame.image = image;
    frame.t_us = 1000;
    frame.width = image.cols;
    frame.height = image.rows;

    eklt_core::SFeatureCandidate candidate;
    candidate.center = cv::Point2d(16, 16);
    candidate.t_us = frame.t_us;

    eklt_core::CFramePatchProvider patch_provider(frame);
    eklt_core::SLocalFeaturePatch local_patch;
    REQUIRE(patch_provider.requestPatch(candidate, 2, &local_patch));

    eklt_core::SPhotometricPatch patch(1, candidate.center, frame.t_us, 5, 4, 2);
    patch.gradient_x = local_patch.gradient_x.clone();
    patch.gradient_y = local_patch.gradient_y.clone();
    patch.insert(MakeEvent(16, 16, 1, 1010));
    patch.insert(MakeEvent(17, 16, -1, 1020));
    patch.insert(MakeEvent(16, 17, 1, 1030));
    patch.insert(MakeEvent(17, 17, -1, 1040));

    // Bootstrap the flow direction from the local event frame before invoking
    // the Ceres refinement against the cached initialization image.
    cv::Mat event_frame;
    REQUIRE(patch.getEventFrameAndReset(&event_frame));
    eklt_core::CPhotometricOptimizer::bootstrapFlowFromEventFrame(&patch, event_frame);
    REQUIRE(patch.initialized);

    eklt_core::CPhotometricOptimizer optimizer(3);
    optimizer.precomputeGradientImage(image, frame.t_us, 1);
    REQUIRE(optimizer.optimize(event_frame, &patch));

    // A successful solve must leave every externally consumed state value
    // finite.
    CHECK(std::isfinite(patch.center.x));
    CHECK(std::isfinite(patch.center.y));
    CHECK(std::isfinite(patch.flow_angle));
    CHECK(std::isfinite(patch.tracking_quality));
}

TEST_CASE("Photometric optimizer rejects inconsistent event-frame geometry", "[eklt_core]")
{
    // Deliberately provide a non-square frame that cannot match the 5x5 patch
    // contract.
    const cv::Mat image = MakeCornerImage();
    eklt_core::SPhotometricPatch patch(1, cv::Point2d(16, 16), 1000, 5, 4, 2);
    const cv::Mat invalid_event_frame = cv::Mat::zeros(4, 5, CV_64F);

    eklt_core::CPhotometricOptimizer optimizer(3);
    optimizer.precomputeGradientImage(image, patch.t_init_us, 1);
    CHECK_FALSE(optimizer.optimize(invalid_event_frame, &patch));
}

TEST_CASE("Photometric optimizer releases gradient cache after its final reference", "[eklt_core]")
{
    // Retain one cached image for two patches and provide a valid local event
    // frame that can distinguish a present cache from an evicted one.
    const cv::Mat image = MakeCornerImage();
    eklt_core::SPhotometricPatch patch(
        1, cv::Point2d(16, 16), 1000, 5, 4, 2);
    cv::Mat event_frame = cv::Mat::zeros(5, 5, CV_64F);
    event_frame.at<double>(2, 2) = 1.0;

    eklt_core::CPhotometricOptimizer optimizer(3);
    optimizer.precomputeGradientImage(image, patch.t_init_us, 2);

    // The first release preserves the shared cache, while the second release
    // erases it and makes later optimization fail without mutating state.
    REQUIRE(optimizer.releaseGradientImageReference(patch.t_init_us));
    REQUIRE(optimizer.optimize(event_frame, &patch));
    REQUIRE(optimizer.releaseGradientImageReference(patch.t_init_us));
    CHECK_FALSE(optimizer.optimize(event_frame, &patch));
    CHECK_FALSE(optimizer.releaseGradientImageReference(patch.t_init_us));
}

TEST_CASE("Photometric optimizer rejects caches without patch references", "[eklt_core]")
{
    // Reject invalid ownership counts before inserting a timestamped gradient
    // cache so callers cannot create storage that has no matching release.
    const cv::Mat image = MakeCornerImage();
    eklt_core::CPhotometricOptimizer optimizer(3);

    CHECK_THROWS_AS(optimizer.precomputeGradientImage(image, 1000, 0),
                    std::invalid_argument);
    CHECK_FALSE(optimizer.releaseGradientImageReference(1000));

    CHECK_THROWS_AS(optimizer.precomputeGradientImage(image, 1001, -1),
                    std::invalid_argument);
    CHECK_FALSE(optimizer.releaseGradientImageReference(1001));
}

TEST_CASE("Photometric gradients honor a validated logarithm offset",
          "[eklt_core]")
{
    const cv::Mat image = MakeCornerImage();
    cv::Mat default_gradient_x;
    cv::Mat default_gradient_y;
    cv::Mat custom_gradient_x;
    cv::Mat custom_gradient_y;

    eklt_core::CPhotometricOptimizer::computeLogGradients(image, &default_gradient_x,
                                                          &default_gradient_y);
    eklt_core::CPhotometricOptimizer::computeLogGradients(image, &custom_gradient_x,
                                                          &custom_gradient_y, 0.25);

    // The ROS1 compatibility flag must reach the native computation instead of
    // silently retaining the native default.
    REQUIRE_FALSE(default_gradient_x.empty());
    REQUIRE_FALSE(custom_gradient_x.empty());
    CHECK(cv::norm(default_gradient_x - custom_gradient_x) > 0.0);
    CHECK(cv::norm(default_gradient_y - custom_gradient_y) > 0.0);

    eklt_core::CPhotometricOptimizer::computeLogGradients(image, &custom_gradient_x,
                                                          &custom_gradient_y, 0.0);
    CHECK(custom_gradient_x.empty());
    CHECK(custom_gradient_y.empty());

    eklt_core::CPhotometricOptimizer optimizer(3);
    CHECK_THROWS_AS(optimizer.precomputeGradientImage(image, 1002, 1, 0.0),
                    std::invalid_argument);
    CHECK_FALSE(optimizer.releaseGradientImageReference(1002));
}

TEST_CASE("Adaptive batch sizing preserves the legacy EKLT equation",
          "[eklt_core]")
{
    const cv::Mat gradient_x = cv::Mat::ones(5, 5, CV_64F);
    const cv::Mat gradient_y = cv::Mat::zeros(5, 5, CV_64F);
    const double flow_angle = 0.0;
    const double displacement_px = 0.6;
    const int configured_limit = 300;

    // The removed ROS1 implementation truncated the projected L1 energy to an
    // integer, then clamped it between five and the configured ceiling.
    const cv::Mat projected =
        displacement_px * std::cos(flow_angle) * gradient_x +
        displacement_px * std::sin(flow_angle) * gradient_y;
    const int legacy_batch_size =
        std::max(5, static_cast<int>(std::min(cv::norm(projected, cv::NORM_L1),
                                              static_cast<double>(configured_limit))));
    const int native_batch_size =
        eklt_core::CPhotometricOptimizer::computeAdaptiveBatchSize(gradient_x, gradient_y,
                                                                   flow_angle, displacement_px,
                                                                   configured_limit);

    CHECK(native_batch_size == legacy_batch_size);
}
