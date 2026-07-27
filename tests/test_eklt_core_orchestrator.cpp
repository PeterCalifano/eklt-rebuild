/// @file test_eklt_core_orchestrator.cpp
/// @brief Verifies complete EKLT orchestration through the ROS-free C++ API.
/// @details Exercises frame-backed and event-only initialization, deterministic
///          event acceptance, feature retirement, gradient-cache release, and
///          reset behavior without middleware types.

#define CATCH_CONFIG_PREFIX_ALL
#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

#include <opencv2/imgproc.hpp>

#include "eklt_core/tracker_orchestrator.h"

namespace
{

    /// @brief Create a compact configuration for deterministic native tests.
    /// @return Valid frame-backed tracker configuration.
    eklt_core::SEkltTrackerConfig MakeConfig()
    {
        eklt_core::SEkltTrackerConfig config;
        config.width = 64;
        config.height = 64;
        config.max_corners = 4;
        config.min_corners = 0;
        config.min_distance = 2.0;
        config.quality_level = 0.01;
        config.block_size = 3;
        config.patch_size = 5;
        config.batch_size = 20;
        config.update_every_n_events = 5;
        config.max_num_iterations = 2;
        config.lk_window_size = 5;
        config.num_pyramidal_layers = 0;
        config.tracking_quality = 0.0;
        config.reconstruction_interval_events = 4;
        return config;
    }

    /// @brief Create a scalar frame containing stable Harris corners.
    /// @param t_us Absolute frame timestamp in microseconds.
    /// @return Valid tracker image with configured test geometry.
    eklt_core::SImageFrame MakeCornerFrame(int64_t t_us)
    {
        cv::Mat image(64, 64, CV_8U, cv::Scalar(0));
        cv::rectangle(image, cv::Point(12, 12), cv::Point(52, 52), cv::Scalar(220), -1);
        cv::line(image, cv::Point(12, 12), cv::Point(52, 52), cv::Scalar(40), 2);

        eklt_core::SImageFrame frame;
        frame.image = image;
        frame.t_us = t_us;
        frame.width = image.cols;
        frame.height = image.rows;
        return frame;
    }

    /// @brief Create one signed native event.
    /// @param x Sensor x coordinate.
    /// @param y Sensor y coordinate.
    /// @param t_us Absolute event timestamp.
    /// @return Positive-polarity event sample.
    eklt_core::SEventSample MakeEvent(uint16_t x, uint16_t y, int64_t t_us)
    {
        eklt_core::SEventSample event;
        event.x = x;
        event.y = y;
        event.p = 1;
        event.t_us = t_us;
        return event;
    }

} // namespace

CATCH_TEST_CASE("Native orchestrator validates fixed sensor configuration",
                "[eklt_core][orchestrator]")
{
    // Reject geometry before constructing any optimizer or reconstruction
    // state that an interface layer would otherwise need to unwind.
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.width = 0;

    CATCH_CHECK_THROWS_AS(eklt_core::CEkltTrackerOrchestrator(config), std::invalid_argument);

    config = MakeConfig();
    config.patch_size = 65;
    CATCH_CHECK_THROWS_AS(eklt_core::CEkltTrackerOrchestrator(config), std::invalid_argument);
}

CATCH_TEST_CASE("Frame-backed orchestration initializes owning track snapshots",
                "[eklt_core][orchestrator]")
{
    // Initialize detection, patch gradients, optimizer cache references, and
    // emitted track rows through one middleware-independent call.
    eklt_core::CEkltTrackerOrchestrator tracker(MakeConfig());
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));
    CATCH_REQUIRE(tracker.initialized());
    CATCH_REQUIRE(tracker.activeTrackCount() > 0);
    CATCH_CHECK(tracker.gradientCacheCount() == 1);

    const eklt_core::STrackerSnapshot snapshot = tracker.snapshot();
    CATCH_REQUIRE(snapshot.valid());
    CATCH_CHECK(snapshot.image.t_us == 100);
    CATCH_CHECK(snapshot.statistics.active_tracks == tracker.activeTrackCount());
    CATCH_CHECK(snapshot.tracks.size() == static_cast<std::size_t>(tracker.config().max_corners));

    const std::vector<eklt_core::STrackSample> samples = tracker.takeTrackSamples();
    CATCH_CHECK(samples.size() == static_cast<std::size_t>(tracker.activeTrackCount()));
    CATCH_CHECK(tracker.takeTrackSamples().empty());
}

CATCH_TEST_CASE("Frame-backed orchestration orders batches and rejects regression",
                "[eklt_core][orchestrator]")
{
    eklt_core::CEkltTrackerOrchestrator tracker(MakeConfig());
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));

    // Stably sort one unsorted transport batch, then enforce monotonicity
    // across subsequent native calls before any counter or patch is mutated.
    const std::vector<eklt_core::SEventSample> unordered_events = {
        MakeEvent(2, 2, 202),
        MakeEvent(2, 2, 200),
        MakeEvent(2, 2, 201),
    };
    CATCH_REQUIRE(tracker.acceptEvents(unordered_events));
    CATCH_CHECK(tracker.statistics().accepted_events == 3);
    CATCH_CHECK(tracker.statistics().processed_events == 3);

    // A frame arriving behind already processed event time cannot restore an
    // obsolete causal image state.
    CATCH_CHECK_FALSE(tracker.acceptFrame(MakeCornerFrame(201)));

    CATCH_CHECK_THROWS_AS(tracker.acceptEvents({MakeEvent(2, 2, 201)}), std::invalid_argument);
    CATCH_CHECK(tracker.statistics().accepted_events == 3);
}

CATCH_TEST_CASE("KLT retirement releases the final native gradient cache",
                "[eklt_core][orchestrator]")
{
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.lk_max_error = 0.0;
    eklt_core::CEkltTrackerOrchestrator tracker(config);
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));
    CATCH_REQUIRE(tracker.activeTrackCount() > 0);
    CATCH_REQUIRE(tracker.gradientCacheCount() == 1);

    // Advance to a non-finite image that normalizes to a non-informative KLT
    // input, then verify each retirement releases its exact cache reference.
    eklt_core::SImageFrame invalid_klt_frame = MakeCornerFrame(200);
    invalid_klt_frame.image.convertTo(invalid_klt_frame.image, CV_32F);
    invalid_klt_frame.image.setTo(cv::Scalar(std::numeric_limits<float>::quiet_NaN()));
    CATCH_REQUIRE(tracker.acceptFrame(invalid_klt_frame));
    CATCH_REQUIRE(tracker.acceptEvents({MakeEvent(2, 2, 201)}));

    CATCH_CHECK(tracker.activeTrackCount() == 0);
    CATCH_CHECK(tracker.gradientCacheCount() == 0);
    CATCH_CHECK(tracker.statistics().lost_count > 0);
}

CATCH_TEST_CASE("Event-only orchestration reconstructs without middleware state",
                "[eklt_core][orchestrator]")
{
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.width = 32;
    config.height = 24;
    config.initialization_mode = eklt_core::ETrackerInitializationMode::EventOnlyFibar;
    config.bootstrap_mode = eklt_core::ETrackerBootstrapMode::Events;
    eklt_core::CEkltTrackerOrchestrator tracker(config);

    // The first complete event batch establishes FIBAR time, produces a
    // causal image, and initializes the same native state used by frame mode.
    // Those image-forming events are not replayed into newly created patches.
    const std::vector<eklt_core::SEventSample> events = {
        MakeEvent(8, 8, 100),
        MakeEvent(9, 8, 101),
        MakeEvent(9, 9, 102),
        MakeEvent(8, 9, 103),
    };
    CATCH_REQUIRE(tracker.acceptEvents(events));
    CATCH_REQUIRE(tracker.initialized());

    const eklt_core::STrackerSnapshot snapshot = tracker.snapshot();
    CATCH_REQUIRE(snapshot.valid());
    CATCH_CHECK(snapshot.image.width == config.width);
    CATCH_CHECK(snapshot.image.height == config.height);
    CATCH_CHECK(snapshot.image.image.type() == CV_32F);
    CATCH_CHECK(snapshot.statistics.accepted_events == events.size());
    CATCH_CHECK(snapshot.statistics.processed_events == 0);

    // Only subsequent causal events enter patch tracking; the orchestrator
    // retains no unbounded pre-initialization transport queue.
    const std::vector<eklt_core::SEventSample> tracking_events = {
        MakeEvent(8, 8, 104),
        MakeEvent(9, 8, 105),
        MakeEvent(9, 9, 106),
        MakeEvent(8, 9, 107),
    };
    CATCH_REQUIRE(tracker.acceptEvents(tracking_events));
    CATCH_CHECK(tracker.statistics().accepted_events == events.size() + tracking_events.size());
    CATCH_CHECK(tracker.statistics().processed_events == tracking_events.size());
}

CATCH_TEST_CASE("Native reset clears reconstruction and feature lifetimes",
                "[eklt_core][orchestrator]")
{
    eklt_core::CEkltTrackerOrchestrator tracker(MakeConfig());
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));
    CATCH_REQUIRE(tracker.initialized());

    // Reset is the only lifecycle operation required by reusable C++ and
    // generated-language callers; it retains configuration but no old state.
    tracker.reset();

    CATCH_CHECK_FALSE(tracker.initialized());
    CATCH_CHECK(tracker.activeTrackCount() == 0);
    CATCH_CHECK(tracker.gradientCacheCount() == 0);
    CATCH_CHECK_FALSE(tracker.snapshot().valid());
    CATCH_CHECK(tracker.takeTrackSamples().empty());
    CATCH_CHECK(tracker.statistics().accepted_events == 0);
    CATCH_CHECK(tracker.config().width == 64);
}
