/// @file main.cpp
/// @brief Verifies the available ROS-free targets of an installed package.

#include <eklt_core/image_normalization.h>
#include <eklt_core/initialization_providers.h>

#ifdef EKLT_CONSUMER_WITH_FIBAR
#include <event_recon_fibar_core/fibar_reconstructor.h>
#endif

#ifdef EKLT_CONSUMER_WITH_CERES
#include <eklt_core/photometric_patch_tracker.h>
#endif

#ifdef EKLT_CONSUMER_WITH_ADAPTERS
#include <event_recon_fibar_adapters/fibar_adapters.h>
#endif

#ifdef EKLT_CONSUMER_WITH_FIBAR
static_assert(
    __cplusplus >= 201703L,
    "The installed FIBAR target must publish its C++17 requirement");
#else
static_assert(
    __cplusplus == 201103L,
    "The ROS-free core-only package must remain consumable as C++11");
#endif

int main()
{
    // Exercise the always-installed OpenCV-backed provider header.
    eklt_core::SFrameHarrisConfig harris_config;
    harris_config.max_corners = 4;

    // Exercise the optional FIBAR facade only when the configured package
    // exported its compiled reconstruction target.
#ifdef EKLT_CONSUMER_WITH_FIBAR
    event_recon_fibar_core::SFibarConfig config;
    config.width = 4;
    config.height = 3;
    config.use_spatial_filter = false;

    event_recon_fibar_core::CFibarReconstructor reconstructor(config);
    if (reconstructor.width() != 4 || reconstructor.height() != 3) {
        return 1;
    }
#endif

#ifdef EKLT_CONSUMER_WITH_ADAPTERS
    // Exercise the Eigen-backed adapter when that target was exported.
    event_recon_fibar_adapters::CFibarReconstructorAdapter adapter(
        4, 3, 10000, 0.5, false);
    if (adapter.width() != 4 || adapter.height() != 3) {
        return 1;
    }
#endif

    return harris_config.max_corners == 4 ? 0 : 1;
}
