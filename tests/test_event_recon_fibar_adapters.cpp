/// @file test_event_recon_fibar_adapters.cpp
/// @brief Verifies Eigen conversion and validation at the FIBAR adapter boundary.

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <limits>
#include <stdexcept>

#include "event_recon_fibar_adapters/fibar_adapters.h"

using Catch::Approx;

namespace
{

gtsam::Vector MakeVector(std::initializer_list<double> values)
{
    gtsam::Vector output(static_cast<Eigen::Index>(values.size()));
    Eigen::Index index = 0;
    for (const double value : values) {
        output(index) = value;
        ++index;
    }
    return output;
}

event_recon_fibar_adapters::CFibarReconstructorAdapter MakeAdapter()
{
    return event_recon_fibar_adapters::CFibarReconstructorAdapter(
        6, 5, 10000, 0.5, false);
}

} // namespace

TEST_CASE(
    "FIBAR adapter accepts integral Eigen arrays atomically",
    "[event_recon_fibar_adapters]")
{
    auto adapter = MakeAdapter();
    const gtsam::Vector x = MakeVector({2.0, 3.0, 2.0, 3.0});
    const gtsam::Vector y = MakeVector({2.0, 2.0, 3.0, 3.0});
    const gtsam::Vector polarity = MakeVector({1.0, -1.0, 1.0, -1.0});
    const gtsam::Vector timestamps = MakeVector({10.0, 20.0, 30.0, 40.0});

    adapter.acceptEvents(x, y, polarity, timestamps);

    const gtsam::Matrix image = adapter.requestImage(40);
    CHECK(adapter.latestTimestampUs() == 40);
    CHECK(image.rows() == 5);
    CHECK(image.cols() == 6);
    CHECK(image.allFinite());
}

TEST_CASE(
    "FIBAR adapter rejects invalid Eigen values without partial mutation",
    "[event_recon_fibar_adapters]")
{
    auto adapter = MakeAdapter();
    adapter.acceptEvent(2, 2, 1, 40);

    const gtsam::Vector x = MakeVector({2.0, 3.0});
    const gtsam::Vector y = MakeVector({2.0, 3.0});
    const gtsam::Vector polarity = MakeVector({1.0, -1.0});

    SECTION("fractional coordinate")
    {
        const gtsam::Vector invalid_x = MakeVector({2.0, 3.5});
        const gtsam::Vector timestamps = MakeVector({50.0, 60.0});
        CHECK_THROWS_AS(
            adapter.acceptEvents(
                invalid_x, y, polarity, timestamps),
            std::invalid_argument);
    }

    SECTION("non-finite polarity")
    {
        const gtsam::Vector invalid_polarity =
            MakeVector({1.0, std::numeric_limits<double>::infinity()});
        const gtsam::Vector timestamps = MakeVector({50.0, 60.0});
        CHECK_THROWS_AS(
            adapter.acceptEvents(
                x, y, invalid_polarity, timestamps),
            std::invalid_argument);
    }

    SECTION("timestamp above int64 maximum")
    {
        const gtsam::Vector timestamps =
            MakeVector({50.0, std::ldexp(1.0, 63)});
        CHECK_THROWS_AS(
            adapter.acceptEvents(x, y, polarity, timestamps),
            std::invalid_argument);
    }

    CHECK(adapter.latestTimestampUs() == 40);
}

TEST_CASE(
    "FIBAR patch adapter validates and exposes row-major patch storage",
    "[event_recon_fibar_adapters]")
{
    event_recon_fibar_core::SLocalFeaturePatch patch;
    patch.width = 2;
    patch.height = 2;
    patch.intensity = {1.0F, 2.0F, 3.0F, 4.0F};
    patch.gradient_x = {0.1F, 0.2F, 0.3F, 0.4F};
    patch.gradient_y = {-0.1F, -0.2F, -0.3F, -0.4F};
    patch.valid_mask = {1, 0, 1, 1};
    patch.valid_fraction = 0.75F;
    patch.gradient_energy = 0.25F;

    const event_recon_fibar_adapters::CLocalFeaturePatchAdapter adapter(patch);

    const gtsam::Matrix intensity = adapter.intensity();
    const gtsam::Matrix valid_mask = adapter.validMask();
    CHECK(intensity(0, 0) == Approx(1.0));
    CHECK(intensity(1, 1) == Approx(4.0));
    CHECK(valid_mask(0, 1) == Approx(0.0));
    CHECK(valid_mask(1, 1) == Approx(1.0));
    CHECK(adapter.validFraction() == Approx(0.75));

    patch.valid_mask.pop_back();
    CHECK_THROWS_AS(
        event_recon_fibar_adapters::CLocalFeaturePatchAdapter(patch),
        std::invalid_argument);
}
