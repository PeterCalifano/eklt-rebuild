/// @file test_event_recon_fibar_core.cpp
/// @brief Verifies FIBAR facade validation, causality, images, and local patches.
/// @details Covers both accepted state transitions and failure atomicity at the
///          ROS-free boundary around the upstream FIBAR implementation.

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

using Catch::Approx;

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

#include "event_recon_fibar_core/fibar_reconstructor.h"

namespace
{

    /// @brief Construct a small temporal or spatial FIBAR facade fixture.
    /// @param use_spatial_filter Select the spatial upstream implementation.
    /// @return Configured empty reconstructor.
    event_recon_fibar_core::CFibarReconstructor MakeReconstructor(bool use_spatial_filter = false)
    {
        event_recon_fibar_core::SFibarConfig config;
        config.width = 6;
        config.height = 5;
        config.cutoff_time_us = 10000;
        config.fill_ratio = 0.5;
        config.use_spatial_filter = use_spatial_filter;
        return event_recon_fibar_core::CFibarReconstructor(config);
    }

    /// @brief Feed one deterministic in-bounds event batch into a reconstructor.
    /// @param reconstructor Facade that receives the batch.
    void AcceptSimpleEvents(event_recon_fibar_core::CFibarReconstructor &reconstructor)
    {
        const std::vector<uint16_t> x{2, 3, 2, 3};
        const std::vector<uint16_t> y{2, 2, 3, 3};
        const std::vector<int8_t> p{1, -1, 1, -1};
        const std::vector<int64_t> t_us{10, 20, 30, 40};
        const event_recon_fibar_core::SEventBatchView batch{
            x.data(),
            y.data(),
            p.data(),
            t_us.data(),
            x.size(),
            6,
            5,
        };
        reconstructor.acceptEvents(batch);
    }

} // namespace

TEST_CASE("FIBAR facade produces finite float image", "[event_recon_fibar_core]")
{
    // One accepted batch must produce a complete finite image with the latest
    // absolute event timestamp.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    const auto image = reconstructor.requestImage(40);

    REQUIRE(image.width == 6);
    REQUIRE(image.height == 5);
    REQUIRE(image.size == 30);
    REQUIRE(image.t_us == 40);
    CHECK(std::all_of(image.data, image.data + image.size, [](float value)
                      { return std::isfinite(value); }));
    CHECK(image.data[2 + 2 * 6] != Approx(0.0F));
}

TEST_CASE("FIBAR facade reports latest-causal timestamp availability", "[event_recon_fibar_core]")
{
    // Requests before the reconstructed state are rejected while later
    // requests reuse that latest causal state.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    CHECK_FALSE(reconstructor.hasImageFor(39));
    CHECK(reconstructor.hasImageFor(40));
    CHECK(reconstructor.hasImageFor(50));
    CHECK_THROWS_AS(reconstructor.requestImage(39), std::runtime_error);
    CHECK(reconstructor.requestImage(50).t_us <= 50);
}

TEST_CASE("FIBAR facade reset clears and restores either filter mode", "[event_recon_fibar_core]")
{
    // Exercise both owned upstream specializations so reset must rebuild the
    // selected state without retaining timestamps or image availability.
    for (const bool use_spatial_filter : {false, true})
    {
        auto reconstructor = MakeReconstructor(use_spatial_filter);
        AcceptSimpleEvents(reconstructor);
        REQUIRE(reconstructor.hasImageFor(40));

        reconstructor.reset();

        CHECK(reconstructor.latestTimestampUs() == -1);
        CHECK_FALSE(reconstructor.hasImageFor(40));
        CHECK_THROWS_AS(reconstructor.requestImage(40), std::runtime_error);

        // A reset facade must accept a new stream from a fresh relative-time
        // origin and expose the reconstructed state normally.
        AcceptSimpleEvents(reconstructor);
        CHECK(reconstructor.latestTimestampUs() == 40);
        CHECK(reconstructor.hasImageFor(40));
    }
}

TEST_CASE("FIBAR facade preserves absolute timestamps with relative internal clock", "[event_recon_fibar_core]")
{
    // Use a realistic large absolute epoch while keeping the upstream-relative
    // event interval small and representable.
    auto reconstructor = MakeReconstructor();
    const std::vector<uint16_t> x{2, 3, 2, 3};
    const std::vector<uint16_t> y{2, 2, 3, 3};
    const std::vector<int8_t> p{1, -1, 1, -1};
    const int64_t t0_us = 1468941032273177LL;
    const std::vector<int64_t> t_us{t0_us, t0_us + 20, t0_us + 40, t0_us + 60};
    const event_recon_fibar_core::SEventBatchView batch{
        x.data(),
        y.data(),
        p.data(),
        t_us.data(),
        x.size(),
        6,
        5,
    };

    reconstructor.acceptEvents(batch);

    CHECK_FALSE(reconstructor.hasImageFor(t0_us + 59));
    REQUIRE(reconstructor.hasImageFor(t0_us + 60));
    CHECK(reconstructor.requestImage(t0_us + 60).t_us == t0_us + 60);
}

TEST_CASE("FIBAR facade rejects timestamps that regress across batches", "[event_recon_fibar_core]")
{
    // Cross-batch ordering rejection must preserve the last accepted timestamp.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    const std::vector<uint16_t> x{2};
    const std::vector<uint16_t> y{2};
    const std::vector<int8_t> p{1};
    const std::vector<int64_t> t_us{39};
    const event_recon_fibar_core::SEventBatchView batch{
        x.data(),
        y.data(),
        p.data(),
        t_us.data(),
        x.size(),
        6,
        5,
    };

    CHECK_THROWS_AS(reconstructor.acceptEvents(batch), std::invalid_argument);
    CHECK(reconstructor.latestTimestampUs() == 40);
}

TEST_CASE("FIBAR facade rejects an invalid batch without partial mutation", "[event_recon_fibar_core]")
{
    // Place an out-of-bounds event after an otherwise valid event to verify the
    // complete batch is checked before upstream mutation begins.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    const std::vector<uint16_t> invalid_x{2, 6};
    const std::vector<uint16_t> invalid_y{2, 2};
    const std::vector<int8_t> invalid_p{1, 1};
    const std::vector<int64_t> invalid_t_us{50, 60};
    const event_recon_fibar_core::SEventBatchView invalid_batch{
        invalid_x.data(),
        invalid_y.data(),
        invalid_p.data(),
        invalid_t_us.data(),
        invalid_x.size(),
        6,
        5,
    };

    CHECK_THROWS_AS(reconstructor.acceptEvents(invalid_batch), std::out_of_range);
    CHECK(reconstructor.latestTimestampUs() == 40);

    // A subsequent valid batch must still be accepted from the timestamp that
    // preceded the rejected batch.
    const std::vector<uint16_t> valid_x{2};
    const std::vector<uint16_t> valid_y{2};
    const std::vector<int8_t> valid_p{1};
    const std::vector<int64_t> valid_t_us{41};
    const event_recon_fibar_core::SEventBatchView valid_batch{
        valid_x.data(),
        valid_y.data(),
        valid_p.data(),
        valid_t_us.data(),
        valid_x.size(),
        6,
        5,
    };

    REQUIRE_NOTHROW(reconstructor.acceptEvents(valid_batch));
    CHECK(reconstructor.latestTimestampUs() == 41);
}

TEST_CASE("FIBAR facade local patch has shape, borders, gradients, and quality", "[event_recon_fibar_core]")
{
    // Verify a fully in-bounds patch before exercising explicit border
    // invalidation with the same reconstructed state.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    const auto centered = reconstructor.requestPatch(2, 2, 1, 40);

    REQUIRE(centered.width == 3);
    REQUIRE(centered.height == 3);
    REQUIRE(centered.intensity.size() == 9);
    REQUIRE(centered.gradient_x.size() == 9);
    REQUIRE(centered.gradient_y.size() == 9);
    REQUIRE(centered.valid_mask.size() == 9);
    CHECK(centered.valid_fraction == Approx(1.0F));
    CHECK(centered.gradient_energy >= 0.0F);

    const auto border = reconstructor.requestPatch(0, 0, 1, 40);
    const auto valid_count = std::count(border.valid_mask.begin(), border.valid_mask.end(), uint8_t{1});
    CHECK(valid_count == 4);
    CHECK(border.valid_fraction == Approx(4.0F / 9.0F));
}

TEST_CASE("FIBAR facade rejects a patch radius that overflows its odd size", "[event_recon_fibar_core]")
{
    // Reject unsafe patch geometry without changing the reconstruction state.
    auto reconstructor = MakeReconstructor();
    AcceptSimpleEvents(reconstructor);

    CHECK_THROWS_AS(reconstructor.requestPatch(2, 2, std::numeric_limits<int>::max(), 40),
                    std::invalid_argument);
    CHECK(reconstructor.latestTimestampUs() == 40);
}

TEST_CASE("FIBAR display normalization is separate from float image", "[event_recon_fibar_core]")
{
    // Display conversion must map the owned float range into a separate 8-bit
    // result without requiring reconstruction state.
    const float image[] = {-1.0F, 0.0F, 1.0F, 3.0F};

    const auto display = event_recon_fibar_core::NormalizeImageForDisplay(image, 4);

    REQUIRE(display.size() == 4);
    CHECK(display.front() == 0);
    CHECK(display.back() == 255);
}

TEST_CASE("FIBAR display normalization handles the complete finite float range", "[event_recon_fibar_core]")
{
    // Exercise the complete finite float span to require widened range
    // arithmetic in the display-only conversion.
    const float image[] = {
        std::numeric_limits<float>::lowest(),
        0.0F,
        std::numeric_limits<float>::max(),
    };

    const auto display = event_recon_fibar_core::NormalizeImageForDisplay(image, 3);

    REQUIRE(display.size() == 3);
    CHECK(display[0] == 0);
    CHECK(display[1] == 128);
    CHECK(display[2] == 255);
}
