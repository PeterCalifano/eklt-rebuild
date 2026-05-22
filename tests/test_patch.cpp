#include <catch2/catch.hpp>

#include "flags.h"
#include "patch.h"
#include "test_fixtures.h"

namespace
{

    void ConfigurePatchFlags()
    {
        FLAGS_patch_size = 5;
        FLAGS_batch_size = 3;
        FLAGS_update_every_n_events = 2;
    }

} // namespace

TEST_CASE("Patch insert keeps the newest events and clips to batch size", "[patch]")
{
    ConfigurePatchFlags();
    tracker::Patch patch(cv::Point2d(10.0, 10.0), ros::Time(0.0));

    patch.insert(fixtures::MakeEvent(10, 10, 1.0, true));
    patch.insert(fixtures::MakeEvent(10, 10, 2.0, false));
    patch.insert(fixtures::MakeEvent(10, 10, 3.0, true));
    patch.insert(fixtures::MakeEvent(10, 10, 4.0, false));

    REQUIRE(patch.event_buffer_.size() == 3);
    REQUIRE(patch.event_counter_ == 4);
    CHECK(patch.event_buffer_.front().ts.toSec() == Approx(4.0));
    CHECK(patch.event_buffer_.back().ts.toSec() == Approx(2.0));
}

TEST_CASE("Patch event-frame accumulation and midpoint timestamp stay deterministic", "[patch]")
{
    ConfigurePatchFlags();
    tracker::Patch patch(cv::Point2d(10.0, 10.0), ros::Time(0.0));

    patch.insert(fixtures::MakeEvent(10, 10, 1.0, true));
    patch.insert(fixtures::MakeEvent(11, 10, 2.0, false));
    patch.insert(fixtures::MakeEvent(10, 10, 3.0, true));

    cv::Mat event_frame;
    patch.getEventFramesAndReset(event_frame);

    REQUIRE(event_frame.rows == 5);
    REQUIRE(event_frame.cols == 5);

    CHECK(event_frame.at<double>(2, 2) == Approx(1.0));
    CHECK(event_frame.at<double>(2, 3) == Approx(-1.0));
    CHECK(patch.t_curr_.toSec() == Approx(2.0));
    CHECK(patch.event_counter_ == 0);
}
