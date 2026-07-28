/// @file test_feature_track_renderer.cpp
/// @brief Verifies transport-neutral feature-track overlay rendering.
/// @details Exercises deterministic frame/FIBAR backgrounds, annotation
///          options, lost-track omission, and strict input validation.

#define CATCH_CONFIG_PREFIX_ALL
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

#include <opencv2/imgproc.hpp>

#include "visualization/feature_track_renderer.h"

namespace
{

    /// @brief Construct a valid snapshot containing one active feature.
    /// @param floating_point_image Use FIBAR-like `CV_32F` storage when true.
    /// @return Owning snapshot suitable for deterministic rendering.
    eklt_core::STrackerSnapshot MakeSnapshot(bool floating_point_image = false)
    {
        cv::Mat image(24, 32, CV_8U, cv::Scalar(20));
        cv::rectangle(image, cv::Point(4, 4), cv::Point(27, 19), cv::Scalar(180), -1);

        eklt_core::STrackerSnapshot snapshot;
        if (floating_point_image)
        {
            image.convertTo(snapshot.image.image, CV_32F, 0.03, -2.0);
        }
        else
        {
            snapshot.image.image = image;
        }
        snapshot.image.width = image.cols;
        snapshot.image.height = image.rows;
        snapshot.image.t_us = 1000;
        snapshot.t_us = 4000;

        eklt_core::STrackState track;
        track.id = 7;
        track.init_center = cv::Point2d(12.0, 12.0);
        track.center = cv::Point2d(14.0, 13.0);
        track.t_init_us = 1000;
        track.t_curr_us = snapshot.t_us;
        track.half_size = 3;
        track.flow_angle = 0.25;
        track.initialized = true;
        snapshot.tracks.push_back(track);
        return snapshot;
    }

    /// @brief Render one snapshot with a compact deterministic scale.
    /// @param snapshot Snapshot to render.
    /// @param config Optional render policy.
    /// @return Owning rendered image.
    eklt_visualization::SRenderedTrackImage Render(const eklt_core::STrackerSnapshot &snapshot,
                                                   const eklt_visualization::SFeatureTrackRenderConfig &config =
                                                       eklt_visualization::SFeatureTrackRenderConfig())
    {
        return eklt_visualization::RenderFeatureTrackOverlay(snapshot, config, 1000);
    }

} // namespace

CATCH_TEST_CASE("Feature renderer returns deterministic owning BGR storage",
                "[visualization][renderer]")
{
    eklt_visualization::SFeatureTrackRenderConfig config;
    config.scale = 2.0;
    config.arrow_length = 4.0;

    const eklt_visualization::SRenderedTrackImage first = Render(MakeSnapshot(), config);
    const eklt_visualization::SRenderedTrackImage second = Render(MakeSnapshot(), config);

    CATCH_REQUIRE(first.valid());
    CATCH_CHECK(first.width == 64);
    CATCH_CHECK(first.height == 48);
    CATCH_CHECK(first.step == 192);
    CATCH_CHECK(first.t_us == 4000);
    CATCH_CHECK(first.pixels == second.pixels);
}

CATCH_TEST_CASE("Feature renderer supports reconstructed float backgrounds",
                "[visualization][renderer]")
{
    eklt_visualization::SFeatureTrackRenderConfig config;
    config.scale = 1.0;

    const eklt_visualization::SRenderedTrackImage rendered =
        Render(MakeSnapshot(true), config);

    CATCH_REQUIRE(rendered.valid());
    CATCH_CHECK(rendered.width == 32);
    CATCH_CHECK(rendered.height == 24);
    CATCH_CHECK(*std::max_element(rendered.pixels.begin(), rendered.pixels.end()) > 0U);
}

CATCH_TEST_CASE("Feature renderer omits lost tracks and honors annotation options",
                "[visualization][renderer]")
{
    eklt_core::STrackerSnapshot lost_snapshot = MakeSnapshot();
    lost_snapshot.tracks.front().lost = true;
    eklt_core::STrackerSnapshot empty_snapshot = lost_snapshot;
    empty_snapshot.tracks.clear();

    eklt_visualization::SFeatureTrackRenderConfig config;
    config.scale = 2.0;
    const eklt_visualization::SRenderedTrackImage lost_render =
        Render(lost_snapshot, config);
    const eklt_visualization::SRenderedTrackImage empty_render =
        Render(empty_snapshot, config);
    CATCH_CHECK(lost_render.pixels == empty_render.pixels);

    const eklt_visualization::SRenderedTrackImage plain_render =
        Render(MakeSnapshot(), config);
    config.draw_patch_outlines = true;
    config.draw_feature_ids = true;
    const eklt_visualization::SRenderedTrackImage annotated_render =
        Render(MakeSnapshot(), config);
    CATCH_CHECK(plain_render.pixels != annotated_render.pixels);
}

CATCH_TEST_CASE("Feature renderer rejects unsafe public inputs",
                "[visualization][renderer]")
{
    eklt_visualization::SFeatureTrackRenderConfig config;
    config.scale = 0.0;
    CATCH_CHECK_THROWS_AS(Render(MakeSnapshot(), config), std::invalid_argument);

    config = eklt_visualization::SFeatureTrackRenderConfig();
    config.arrow_length = std::numeric_limits<double>::infinity();
    CATCH_CHECK_THROWS_AS(Render(MakeSnapshot(), config), std::invalid_argument);

    eklt_core::STrackerSnapshot invalid_time = MakeSnapshot();
    invalid_time.t_us = 999;
    CATCH_CHECK_THROWS_AS(
        eklt_visualization::RenderFeatureTrackOverlay(invalid_time,
                                                      config,
                                                      1000),
        std::invalid_argument);

    eklt_core::STrackerSnapshot invalid_track = MakeSnapshot();
    invalid_track.tracks.front().center.x = std::numeric_limits<double>::quiet_NaN();
    CATCH_CHECK_THROWS_AS(Render(invalid_track, config), std::invalid_argument);
}

CATCH_TEST_CASE("Feature renderer checks conversion after output-space scaling",
                "[visualization][renderer]")
{
    // Keep finite wrapper-supplied coordinates in floating-point form until
    // the renderer applies its checked output-space conversion.
    eklt_core::STrackerSnapshot large_track = MakeSnapshot();
    const double beyond_integer_range =
        static_cast<double>(std::numeric_limits<int>::max()) + 1024.0;
    large_track.tracks.front().init_center =
        cv::Point2d(beyond_integer_range, beyond_integer_range);
    large_track.tracks.front().center =
        cv::Point2d(beyond_integer_range, beyond_integer_range);
    eklt_visualization::SFeatureTrackRenderConfig config;
    config.scale = 0.05;
    config.draw_feature_ids = true;
    CATCH_CHECK(Render(large_track, config).valid());
}
