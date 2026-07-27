/// @file test_tracker_utils.cpp
/// @brief Verifies ordered ROS1 buffering and exact timestamp conversion.
/// @details Covers stable insertion, causal image selection, and the integer
///          microsecond native boundary retained for legacy consumers.

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <limits>
#include <stdexcept>

#include "test_fixtures.h"
#include "tracker_utils.h"

using Catch::Approx;

TEST_CASE("ROS timestamps round-trip at native microsecond precision",
          "[tracker_utils]")
{
    const ros::Time timestamp(123, 456789123);
    const int64_t timestamp_us = tracker::RosTimeToUs(timestamp);

    CHECK(timestamp_us == 123456789);
    CHECK(tracker::RosTimeFromUs(timestamp_us) == ros::Time(123, 456789000));
    CHECK_THROWS_AS(tracker::RosTimeFromUs(-1), std::invalid_argument);
    CHECK_THROWS_AS(tracker::RosTimeFromUs(std::numeric_limits<int64_t>::max()),
                    std::invalid_argument);
}

TEST_CASE("Sorted event insertion keeps the buffer in timestamp order", "[tracker_utils]")
{
    tracker::EventBuffer events;

    tracker::InsertEventInSortedOrder(events, fixtures::MakeEvent(1, 1, 3.0, true));
    tracker::InsertEventInSortedOrder(events, fixtures::MakeEvent(2, 1, 1.0, true));
    tracker::InsertEventInSortedOrder(events, fixtures::MakeEvent(3, 1, 2.0, false));
    tracker::InsertEventInSortedOrder(events, fixtures::MakeEvent(4, 1, 2.0, true));

    REQUIRE(events.size() == 4);
    CHECK(events[0].ts.toSec() == Approx(1.0));
    CHECK(events[1].ts.toSec() == Approx(2.0));
    CHECK(events[2].ts.toSec() == Approx(2.0));
    CHECK(events[3].ts.toSec() == Approx(3.0));
    CHECK(events[1].x == 3);
    CHECK(events[2].x == 4);
}

TEST_CASE("Image iterator advances to the latest causal frame",
          "[tracker_utils]")
{
    tracker::ImageBuffer images;
    images.emplace(ros::Time(1.0), cv::Mat());
    images.emplace(ros::Time(2.0), cv::Mat());
    images.emplace(ros::Time(3.0), cv::Mat());
    images.emplace(ros::Time(4.0), cv::Mat());

    auto current = images.begin();

    SECTION("Advance when later frames still remain before the target time")
    {
        const bool advanced =
            tracker::AdvanceToFirstImageBeforeTimestamp(images, ros::Time(3.5), current);

        CHECK(advanced);
        CHECK(current->first.toSec() == Approx(3.0));
    }

    SECTION("Do not advance when the next frame is not strictly before the target time")
    {
        const bool advanced =
            tracker::AdvanceToFirstImageBeforeTimestamp(images, ros::Time(2.0), current);

        CHECK_FALSE(advanced);
        CHECK(current->first.toSec() == Approx(1.0));
    }
}
