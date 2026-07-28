/// @file main.cpp
/// @brief Verifies the available ROS-free targets of an installed package.

#include <eklt_core/image_normalization.h>
#include <eklt_core/initialization_providers.h>
#include <eklt_core/photometric_patch_tracker.h>
#include <eklt_core/tracker_orchestrator.h>
#include <event_recon_fibar_core/fibar_reconstructor.h>
#include <visualization/feature_track_renderer.h>
#include <wrap_adapters/fibar_adapters.h>

static_assert(
    __cplusplus >= 201703L,
    "Every installed EKLT C++ target must publish the C++17 baseline");

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

    // Exercise construction of the complete installed ROS-free tracker.
    eklt_core::SEkltTrackerConfig tracker_config;
    tracker_config.width = 32;
    tracker_config.height = 32;
    eklt_core::CEkltTrackerOrchestrator tracker(tracker_config);
    if (tracker.config().width != 32 || tracker.config().height != 32)
    {
        return 1;
    }
    if (tracker.lastProcessingTiming().valid())
    {
        return 1;
    }

    // Exercise the installed transport-neutral visualization function.
    eklt_core::STrackerSnapshot snapshot;
    snapshot.image.image = cv::Mat(2, 3, CV_8U, cv::Scalar(64));
    snapshot.image.width = snapshot.image.image.cols;
    snapshot.image.height = snapshot.image.image.rows;
    snapshot.image.t_us = 100;
    snapshot.t_us = 200;
    const eklt_visualization::SFeatureTrackRenderConfig render_config;
    const eklt_visualization::SRenderedTrackImage rendered =
        eklt_visualization::RenderFeatureTrackOverlay(snapshot, render_config, 100);
    if (!rendered.valid())
    {
        return 1;
    }

    // Exercise the Eigen-backed convenience API from the same native binary.
    wrap_adapters::CFibarReconstructorAdapter adapter(4, 3, 10000, 0.5, false);
    if (adapter.width() != 4 || adapter.height() != 3)
    {
        return 1;
    }

    return harris_config.max_corners == 4 ? 0 : 1;
}
