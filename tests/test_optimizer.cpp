/// @file test_optimizer.cpp
/// @brief Verifies the legacy ROS1 optimizer adapter against the native API.
/// @details Confirms that established flags reach the consolidated gradient
///          computation and that timestamped patch references can be cached.

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "eklt_core/photometric_patch_tracker.h"
#include "flags.h"
#include "optimizer.h"
#include "patch.h"

using Catch::Approx;

TEST_CASE("ROS1 optimizer delegates logarithm gradients to the native core",
          "[optimizer]")
{
    FLAGS_log_eps = 0.125;
    FLAGS_max_num_iterations = 3;
    const cv::Mat image =
        (cv::Mat_<uint8_t>(3, 3) <<
            0U, 32U, 64U,
            16U, 128U, 192U,
            32U, 192U, 255U);

    nlls::Optimizer ros_optimizer;
    cv::Mat ros_gradient_x;
    cv::Mat ros_gradient_y;
    ros_optimizer.getLogGradients(image, ros_gradient_x, ros_gradient_y);

    cv::Mat native_gradient_x;
    cv::Mat native_gradient_y;
    eklt_core::CPhotometricOptimizer::computeLogGradients(image, &native_gradient_x,
                                                          &native_gradient_y, FLAGS_log_eps);

    REQUIRE_FALSE(ros_gradient_x.empty());
    REQUIRE_FALSE(ros_gradient_y.empty());
    CHECK(cv::norm(ros_gradient_x - native_gradient_x) == Approx(0.0));
    CHECK(cv::norm(ros_gradient_y - native_gradient_y) == Approx(0.0));
}

TEST_CASE("ROS1 optimizer caches only live patch references", "[optimizer]")
{
    FLAGS_patch_size = 5;
    FLAGS_batch_size = 4;
    FLAGS_update_every_n_events = 2;
    FLAGS_log_eps = 0.01;
    FLAGS_max_num_iterations = 3;

    tracker::ImageBuffer images;
    const ros::Time timestamp(12, 345000000);
    const cv::Mat image =
        (cv::Mat_<uint8_t>(5, 5) <<
            0U, 0U, 0U, 0U, 0U,
            0U, 64U, 128U, 64U, 0U,
            0U, 128U, 255U, 128U, 0U,
            0U, 64U, 128U, 64U, 0U,
            0U, 0U, 0U, 0U, 0U);
    const tracker::ImageBuffer::iterator image_it =
        images.emplace(timestamp, image).first;

    nlls::Optimizer optimizer_without_patches;
    tracker::Patches no_patches;
    CHECK_FALSE(optimizer_without_patches.precomputeLogImageArray(no_patches, image_it));

    nlls::Optimizer optimizer_with_patch;
    tracker::Patches patches;
    patches.emplace_back(cv::Point2d(2.0, 2.0), timestamp);
    REQUIRE(optimizer_with_patch.precomputeLogImageArray(patches, image_it));

    ros::Time cache_timestamp = timestamp;
    optimizer_with_patch.decrementCounter(cache_timestamp);
}
