/// @file test_event_packet_adapter.cpp
/// @brief Verifies EventPacket decoding and native event-only orchestration.
/// @details Synthetic scalar frames are differenced at runtime, encoded with
///          the standard mono codec, decoded through the ROS2 adapter, and
///          submitted to the same ROS-free tracker used by every interface.

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <vector>

#include <event_camera_codecs/encoder.h>
#include <event_camera_msgs/msg/event_packet.hpp>
#include <gtest/gtest.h>
#include <opencv2/imgproc.hpp>

#include "eklt_core/tracker_orchestrator.h"
#include "eklt_rebuild/event_packet_decoder.h"

namespace
{

    /// @brief Create a compact event-only configuration for adapter tests.
    /// @return Valid deterministic tracker configuration.
    eklt_core::SEkltTrackerConfig MakeConfig()
    {
        eklt_core::SEkltTrackerConfig config;
        config.width = 64;
        config.height = 64;
        config.initialization_mode = eklt_core::ETrackerInitializationMode::EventOnlyFibar;
        config.bootstrap_mode = eklt_core::ETrackerBootstrapMode::Events;
        config.max_corners = 4;
        config.min_corners = 0;
        config.min_distance = 2.0;
        config.quality_level = 0.01;
        config.block_size = 3;
        config.patch_size = 9;
        config.batch_size = 5;
        config.update_every_n_events = 5;
        config.max_num_iterations = 2;
        config.tracking_quality = 0.0;
        config.reconstruction_interval_events = 4;
        config.fibar_use_spatial_filter = false;
        return config;
    }

    /// @brief Create a scalar image containing translated stable Harris corners.
    /// @param offset_x Horizontal pattern translation in pixels.
    /// @param offset_y Vertical pattern translation in pixels.
    /// @return Eight-bit scalar image with test geometry.
    cv::Mat MakeCornerImage(int offset_x = 0, int offset_y = 0)
    {
        cv::Mat image(64, 64, CV_8U, cv::Scalar(0));
        cv::rectangle(image, cv::Point(12 + offset_x, 12 + offset_y),
                      cv::Point(52 + offset_x, 52 + offset_y), cv::Scalar(220), -1);
        cv::line(image, cv::Point(12 + offset_x, 12 + offset_y),
                 cv::Point(52 + offset_x, 52 + offset_y), cv::Scalar(40), 2);
        return image;
    }

    /// @brief Convert an exact scalar-frame difference into signed events.
    /// @param before Earlier eight-bit image.
    /// @param after Later image with matching geometry.
    /// @param first_t_us Timestamp assigned to the first event.
    /// @return Deterministic row-major signed event sequence.
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

    /// @brief Encode native events as one standard mono EventPacket.
    /// @param events Non-empty events whose time span fits signed nanoseconds.
    /// @param sequence Packet sequence number.
    /// @return Encoded ROS2 packet preserving tuple order.
    event_camera_msgs::msg::EventPacket
    MakePacket(const std::vector<eklt_core::SEventSample> &events,
               uint64_t sequence)
    {
        if (events.empty())
        {
            throw std::invalid_argument("test packet requires events");
        }

        event_camera_msgs::msg::EventPacket packet;
        packet.width = 64;
        packet.height = 64;
        packet.seq = sequence;
        packet.time_base = static_cast<uint64_t>(events.front().t_us) * 1000U;
        packet.encoding = "mono";
        packet.is_bigendian = false;

        const std::shared_ptr<event_camera_codecs::Encoder> encoder =
            event_camera_codecs::Encoder::newInstance(packet.encoding);
        if (!encoder)
        {
            throw std::runtime_error("mono encoder unavailable");
        }
        encoder->setBuffer(&packet.events);
        encoder->setSensorTime(packet.time_base);
        for (const eklt_core::SEventSample &event : events)
        {
            const int64_t delta_ns =
                (event.t_us - events.front().t_us) * static_cast<int64_t>(1000);
            encoder->encodeCD(static_cast<int32_t>(delta_ns), event.x, event.y,
                              static_cast<uint8_t>(event.p > 0 ? 1 : 0));
        }
        encoder->flush();
        return packet;
    }

    /// @brief Run the complete encoded synthetic event sequence once.
    /// @return Native track rows emitted after initialization.
    std::vector<eklt_core::STrackSample> RunSyntheticTracking()
    {
        const eklt_core::SEkltTrackerConfig config = MakeConfig();
        const cv::Mat empty_image = cv::Mat::zeros(config.height, config.width, CV_8U);
        const cv::Mat initial_image = MakeCornerImage();
        const std::vector<eklt_core::SEventSample> initialization_events =
            MakeIdealEvents(empty_image, initial_image, 100);
        const std::vector<eklt_core::SEventSample> tracking_events =
            MakeIdealEvents(initial_image, MakeCornerImage(1, 0),
                            initialization_events.back().t_us + 1);

        eklt_rebuild::CEventPacketDecoder decoder;
        eklt_core::CEkltTrackerOrchestrator tracker(config);
        EXPECT_TRUE(tracker.acceptEvents(decoder.decode(MakePacket(initialization_events, 0))));
        EXPECT_TRUE(tracker.initialized());
        EXPECT_GT(tracker.activeTrackCount(), 0);
        tracker.takeTrackSamples();

        EXPECT_TRUE(tracker.acceptEvents(decoder.decode(MakePacket(tracking_events, 1))));
        EXPECT_GT(tracker.statistics().optimization_updates, 0U);
        return tracker.takeTrackSamples();
    }

} // namespace

TEST(CEventPacketDecoder, PreservesEventTupleOrderAndUnits)
{
    const std::vector<eklt_core::SEventSample> expected = {
        eklt_core::SEventSample{2, 3, 1, 100},
        eklt_core::SEventSample{5, 7, -1, 102},
        eklt_core::SEventSample{11, 13, 1, 109},
    };

    eklt_rebuild::CEventPacketDecoder decoder;
    const std::vector<eklt_core::SEventSample> actual = decoder.decode(MakePacket(expected, 7));

    ASSERT_EQ(actual.size(), expected.size());
    for (std::size_t index = 0; index < expected.size(); ++index)
    {
        EXPECT_EQ(actual[index].x, expected[index].x);
        EXPECT_EQ(actual[index].y, expected[index].y);
        EXPECT_EQ(actual[index].p, expected[index].p);
        EXPECT_EQ(actual[index].t_us, expected[index].t_us);
    }
}

TEST(CEventPacketDecoder, RejectsUnsupportedOrMalformedPackets)
{
    event_camera_msgs::msg::EventPacket packet;
    packet.width = 64;
    packet.height = 64;
    packet.encoding = "unsupported";

    eklt_rebuild::CEventPacketDecoder decoder;
    EXPECT_THROW(decoder.decode(packet), std::invalid_argument);

    packet.encoding = "mono";
    packet.events.resize(7U);
    EXPECT_THROW(decoder.decode(packet), std::invalid_argument);
}

TEST(CEventPacketAdapter, DrivesDeterministicNativeTracking)
{
    const std::vector<eklt_core::STrackSample> first = RunSyntheticTracking();
    const std::vector<eklt_core::STrackSample> second = RunSyntheticTracking();

    ASSERT_FALSE(first.empty());
    ASSERT_EQ(first.size(), second.size());
    for (std::size_t index = 0; index < first.size(); ++index)
    {
        EXPECT_EQ(first[index].id, second[index].id);
        EXPECT_EQ(first[index].t_us, second[index].t_us);
        EXPECT_DOUBLE_EQ(first[index].center.x, second[index].center.x);
        EXPECT_DOUBLE_EQ(first[index].center.y, second[index].center.y);
    }
}
