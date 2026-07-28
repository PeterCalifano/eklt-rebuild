/// @file test_eklt_core_orchestrator.cpp
/// @brief Verifies complete EKLT orchestration through the ROS-free C++ API.
/// @details Exercises frame-backed and event-only initialization, deterministic
///          event acceptance, feature retirement, gradient-cache release, and
///          reset behavior without middleware types.

#define CATCH_CONFIG_PREFIX_ALL
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
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

    /// @brief Create a scalar image containing translated stable Harris corners.
    /// @param offset_x Horizontal pattern translation in pixels.
    /// @param offset_y Vertical pattern translation in pixels.
    /// @return Eight-bit scalar image with configured test geometry.
    cv::Mat MakeCornerImage(int offset_x = 0, int offset_y = 0)
    {
        cv::Mat image(64, 64, CV_8U, cv::Scalar(0));
        cv::rectangle(image, cv::Point(12 + offset_x, 12 + offset_y),
                      cv::Point(52 + offset_x, 52 + offset_y), cv::Scalar(220), -1);
        cv::line(image, cv::Point(12 + offset_x, 12 + offset_y),
                 cv::Point(52 + offset_x, 52 + offset_y), cv::Scalar(40), 2);
        return image;
    }

    /// @brief Create one timestamped frame from the synthetic corner image.
    /// @param t_us Absolute frame timestamp in microseconds.
    /// @param offset_x Horizontal pattern translation in pixels.
    /// @param offset_y Vertical pattern translation in pixels.
    /// @return Valid tracker image with configured test geometry.
    eklt_core::SImageFrame MakeCornerFrame(int64_t t_us,
                                           int offset_x = 0,
                                           int offset_y = 0)
    {
        eklt_core::SImageFrame frame;
        frame.image = MakeCornerImage(offset_x, offset_y);
        frame.t_us = t_us;
        frame.width = frame.image.cols;
        frame.height = frame.image.rows;
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

    /// @brief Convert an exact synthetic frame difference into signed events.
    /// @details Emits one event per changed pixel in deterministic row-major
    ///          order. This idealized test source requires no online simulator.
    /// @param before Earlier eight-bit scalar image.
    /// @param after Later eight-bit scalar image with matching geometry.
    /// @param first_t_us Timestamp assigned to the first changed pixel.
    /// @return Monotonically timestamped positive and negative events.
    std::vector<eklt_core::SEventSample> MakeIdealEvents(const cv::Mat &before,
                                                         const cv::Mat &after,
                                                         int64_t first_t_us)
    {
        if (before.empty() || before.type() != CV_8U || after.type() != CV_8U ||
            before.size() != after.size() || first_t_us < 0)
        {
            throw std::invalid_argument("ideal event frames must be matching CV_8U images");
        }

        std::vector<eklt_core::SEventSample> events;
        events.reserve(before.total());
        int64_t t_us = first_t_us;
        for (int y = 0; y < before.rows; ++y)
        {
            for (int x = 0; x < before.cols; ++x)
            {
                const int difference =
                    static_cast<int>(after.at<uint8_t>(y, x)) -
                    static_cast<int>(before.at<uint8_t>(y, x));
                if (difference == 0)
                {
                    continue;
                }

                events.push_back(eklt_core::SEventSample{
                    static_cast<uint16_t>(x),
                    static_cast<uint16_t>(y),
                    static_cast<int8_t>(difference > 0 ? 1 : -1),
                    t_us,
                });
                ++t_us;
            }
        }
        return events;
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
    const eklt_core::STrackerTimingSample timing =
        tracker.lastProcessingTiming();
    CATCH_REQUIRE(timing.valid());
    CATCH_CHECK(timing.t_us == 202);
    CATCH_CHECK(timing.fibar_ms == 0.0);
    CATCH_CHECK(timing.eklt_ms >= 0.0);
    CATCH_CHECK(timing.native_total_ms >= timing.eklt_ms);

    // A frame arriving behind already processed event time cannot restore an
    // obsolete causal image state.
    CATCH_CHECK_FALSE(tracker.acceptFrame(MakeCornerFrame(201)));

    CATCH_CHECK_THROWS_AS(tracker.acceptEvents({MakeEvent(2, 2, 201)}), std::invalid_argument);
    CATCH_CHECK(tracker.statistics().accepted_events == 3);
    CATCH_CHECK_FALSE(tracker.lastProcessingTiming().valid());
}

CATCH_TEST_CASE("Frame-backed orchestration recovers synthetic image translation",
                "[eklt_core][orchestrator][algorithm]")
{
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.lk_window_size = 11;
    config.num_pyramidal_layers = 1;
    eklt_core::CEkltTrackerOrchestrator tracker(config);
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));
    tracker.takeTrackSamples();

    // Advance the causal image with one scheduler event so the real OpenCV KLT
    // bootstrap observes the known translation between generated frames.
    constexpr int kTranslationX = 3;
    constexpr int kTranslationY = 2;
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(200, kTranslationX, kTranslationY)));
    CATCH_REQUIRE(tracker.acceptEvents({MakeEvent(2, 2, 201)}));

    const eklt_core::STrackerSnapshot snapshot = tracker.snapshot();
    const std::vector<eklt_core::STrackSample> samples = tracker.takeTrackSamples();
    CATCH_REQUIRE(snapshot.valid());
    CATCH_REQUIRE_FALSE(samples.empty());
    for (const eklt_core::STrackState &track : snapshot.tracks)
    {
        if (track.lost)
        {
            continue;
        }

        CATCH_REQUIRE(track.initialized);
        CATCH_CHECK(std::abs(track.center.x - track.init_center.x -
                             static_cast<double>(kTranslationX)) < 0.35);
        CATCH_CHECK(std::abs(track.center.y - track.init_center.y -
                             static_cast<double>(kTranslationY)) < 0.35);
    }
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
                "[eklt_core][orchestrator][algorithm]")
{
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.initialization_mode = eklt_core::ETrackerInitializationMode::EventOnlyFibar;
    config.bootstrap_mode = eklt_core::ETrackerBootstrapMode::Events;
    config.patch_size = 9;
    config.batch_size = 5;
    config.fibar_use_spatial_filter = false;
    eklt_core::CEkltTrackerOrchestrator tracker(config);

    // Generate the first FIBAR image entirely from an ideal frame difference.
    // Image-forming events initialize live native patches but are not replayed
    // as tracking evidence for those newly created patches.
    const cv::Mat empty_image = cv::Mat::zeros(config.height, config.width, CV_8U);
    const cv::Mat initial_image = MakeCornerImage();
    const std::vector<eklt_core::SEventSample> initialization_events =
        MakeIdealEvents(empty_image, initial_image, 100);
    CATCH_REQUIRE_FALSE(initialization_events.empty());
    CATCH_REQUIRE(tracker.acceptEvents(initialization_events));
    CATCH_REQUIRE(tracker.initialized());
    CATCH_REQUIRE(tracker.activeTrackCount() > 0);
    const eklt_core::STrackerTimingSample initialization_timing =
        tracker.lastProcessingTiming();
    CATCH_REQUIRE(initialization_timing.valid());
    CATCH_CHECK(initialization_timing.t_us == initialization_events.back().t_us);
    CATCH_CHECK(initialization_timing.fibar_ms >= 0.0);
    CATCH_CHECK(initialization_timing.eklt_ms >= 0.0);
    CATCH_CHECK(initialization_timing.native_total_ms >=
                initialization_timing.fibar_ms);

    const eklt_core::STrackerSnapshot initial_snapshot = tracker.snapshot();
    CATCH_REQUIRE(initial_snapshot.valid());
    CATCH_CHECK(initial_snapshot.image.width == config.width);
    CATCH_CHECK(initial_snapshot.image.height == config.height);
    CATCH_CHECK(initial_snapshot.image.image.type() == CV_32F);
    CATCH_CHECK(initial_snapshot.statistics.accepted_events == initialization_events.size());
    CATCH_CHECK(initial_snapshot.statistics.processed_events == 0);
    tracker.takeTrackSamples();

    // Diff a translated frame at runtime and require those later events to
    // bootstrap flow, execute Ceres, and emit at least one updated track row.
    const cv::Mat translated_image = MakeCornerImage(1, 0);
    const int64_t first_tracking_t_us = initialization_events.back().t_us + 1;
    const std::vector<eklt_core::SEventSample> tracking_events =
        MakeIdealEvents(initial_image, translated_image, first_tracking_t_us);
    CATCH_REQUIRE(tracker.acceptEvents(tracking_events));
    CATCH_REQUIRE(tracker.activeTrackCount() > 0);
    CATCH_CHECK(tracker.statistics().accepted_events ==
                initialization_events.size() + tracking_events.size());
    CATCH_CHECK(tracker.statistics().processed_events == tracking_events.size());
    std::size_t maximum_local_event_count = 0;
    for (const eklt_core::STrackState &track : initial_snapshot.tracks)
    {
        if (track.lost)
        {
            continue;
        }

        const std::size_t local_event_count =
            static_cast<std::size_t>(std::count_if(
                tracking_events.begin(), tracking_events.end(),
                [&track](const eklt_core::SEventSample &event)
                {
                    return track.half_size >=
                               std::abs(static_cast<double>(event.x) - track.center.x) &&
                           track.half_size >=
                               std::abs(static_cast<double>(event.y) - track.center.y);
                }));
        maximum_local_event_count =
            std::max(maximum_local_event_count, local_event_count);
    }
    CATCH_REQUIRE(maximum_local_event_count >= 5);
    CATCH_REQUIRE(tracker.statistics().optimization_updates > 0);

    const std::vector<eklt_core::STrackSample> updated_samples = tracker.takeTrackSamples();
    CATCH_REQUIRE_FALSE(updated_samples.empty());
    CATCH_CHECK(updated_samples.back().t_us >= first_tracking_t_us);
}

CATCH_TEST_CASE("Frame-backed orchestration reinitializes after synthetic feature loss",
                "[eklt_core][orchestrator][algorithm]")
{
    eklt_core::SEkltTrackerConfig config = MakeConfig();
    config.min_corners = config.max_corners;
    config.lk_max_error = 0.0;
    eklt_core::CEkltTrackerOrchestrator tracker(config);
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(100)));
    const int initial_track_count = tracker.activeTrackCount();
    CATCH_REQUIRE(initial_track_count > 0);
    tracker.takeTrackSamples();

    // Force all initial KLT tracks to retire on a non-informative frame. The
    // invalid image cannot immediately supply replacement candidates.
    eklt_core::SImageFrame lost_frame = MakeCornerFrame(200);
    lost_frame.image.convertTo(lost_frame.image, CV_32F);
    lost_frame.image.setTo(cv::Scalar(std::numeric_limits<float>::quiet_NaN()));
    CATCH_REQUIRE(tracker.acceptFrame(lost_frame));
    CATCH_REQUIRE(tracker.acceptEvents({MakeEvent(2, 2, 201)}));
    CATCH_REQUIRE(tracker.activeTrackCount() == 0);
    CATCH_REQUIRE(tracker.gradientCacheCount() == 0);

    // A later valid causal frame must refill the retired stable slots with new
    // track identities and establish one balanced gradient cache.
    CATCH_REQUIRE(tracker.acceptFrame(MakeCornerFrame(300, 2, 1)));
    CATCH_REQUIRE(tracker.acceptEvents({MakeEvent(2, 2, 301)}));
    CATCH_REQUIRE(tracker.activeTrackCount() == initial_track_count);
    CATCH_CHECK(tracker.gradientCacheCount() == 1);
    CATCH_CHECK(tracker.statistics().initialization_count == 2);
    CATCH_CHECK(tracker.statistics().last_initialized_count == initial_track_count);

    const std::vector<eklt_core::STrackSample> replacement_samples =
        tracker.takeTrackSamples();
    CATCH_REQUIRE(replacement_samples.size() ==
                  static_cast<std::size_t>(initial_track_count));
    for (const eklt_core::STrackSample &sample : replacement_samples)
    {
        CATCH_CHECK(sample.id >= initial_track_count);
        CATCH_CHECK(sample.t_us == 300);
    }
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
    CATCH_CHECK_FALSE(tracker.lastProcessingTiming().valid());
    CATCH_CHECK(tracker.config().width == 64);
}
