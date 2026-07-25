/// @file main.cpp
/// @brief Verifies the available ROS-free targets of an installed package.

#include <eklt_core/image_normalization.h>
#include <eklt_core/initialization_providers.h>
#include <event_recon_fibar_adapters/fibar_adapters.h>
#include <event_recon_fibar_core/fibar_reconstructor.h>

#ifdef EKLT_CONSUMER_WITH_CERES
#include <eklt_core/photometric_patch_tracker.h>
#endif

static_assert(
    __cplusplus >= 201703L,
    "The installed native target must publish its C++17 requirement");

int main()
{
    // Exercise the always-installed OpenCV-backed provider header.
    eklt_core::SFrameHarrisConfig harris_config;
    harris_config.max_corners = 4;

    // Exercise the native facade compiled into libeklt-rebuild.
    event_recon_fibar_core::SFibarConfig config;
    config.width = 4;
    config.height = 3;
    config.use_spatial_filter = false;

    event_recon_fibar_core::CFibarReconstructor reconstructor(config);
    if (reconstructor.width() != 4 || reconstructor.height() != 3)
    {
        return 1;
    }

    // Exercise the Eigen-backed convenience API from the same native binary.
    event_recon_fibar_adapters::CFibarReconstructorAdapter adapter(
        4, 3, 10000, 0.5, false);
    if (adapter.width() != 4 || adapter.height() != 3)
    {
        return 1;
    }

    return harris_config.max_corners == 4 ? 0 : 1;
}
