/// @file flags.cpp
/// @brief Defines the ROS1 overlay runtime flags.
/// @details The frame-backed configuration remains the default; event-only
///          FIBAR reconstruction is enabled explicitly.

#include "flags.h"

// Feature detection.
DEFINE_int32(max_corners, 100,
             "Maximum features allowed to be tracked.");
DEFINE_int32(min_corners, 60,
             "Minimum features allowed to be tracked.");
DEFINE_int32(min_distance, 30,
             "Minimum distance between detected Harris features.");
DEFINE_int32(block_size, 30,
             "Neighborhood size used by the Harris detector.");

DEFINE_double(k, 0.04,
              "Harris detector free parameter.");
DEFINE_double(quality_level, 0.3,
              "Minimum Harris response relative to the strongest corner.");
DEFINE_double(log_eps, 1e-2,
              "Positive intensity offset applied before log-image gradients.");
DEFINE_double(first_image_t, -1,
              "Discard frame images before this timestamp in seconds.");
DEFINE_string(tracks_file_txt, "",
              "Optional output path for rows formatted as id time_s x_px y_px.");

// Event tracking and optimization.
DEFINE_int32(lk_window_size, 15,
             "KLT window size used for frame-backed flow bootstrapping.");
DEFINE_int32(num_pyramidal_layers, 2,
             "KLT pyramid depth used for frame-backed flow bootstrapping.");
DEFINE_int32(batch_size, 200,
             "Maximum retained events in each photometric patch.");
DEFINE_int32(patch_size, 25,
             "Odd side length of each tracked photometric patch.");
DEFINE_int32(max_num_iterations, 10,
             "Maximum Ceres iterations for each photometric update.");

DEFINE_double(displacement_px, 0.6,
              "Target displacement used by adaptive event-batch sizing.");
DEFINE_double(tracking_quality, 0.4,
              "Minimum accepted native photometric tracking quality.");
DEFINE_string(bootstrap, "",
              "Optical-flow bootstrap mode: 'klt' or 'events'.");
DEFINE_bool(event_only_mode, false,
            "Use periodic FIBAR reconstructions instead of frame subscription.");
DEFINE_int32(event_only_reconstruction_interval_events, 5000,
             "Accepted events between event-only initialization images.");
DEFINE_uint32(fibar_cutoff_time_us, 10000,
              "FIBAR temporal cutoff in microseconds.");
DEFINE_double(fibar_fill_ratio, 0.5,
              "FIBAR spatial-filter fill ratio.");
DEFINE_bool(fibar_use_spatial_filter, true,
            "Use FIBAR spatial filtering instead of temporal filtering.");

// Viewer.
DEFINE_int32(update_every_n_events, 20,
             "Tracked events between viewer snapshot updates.");
DEFINE_double(scale, 4,
              "Nearest-neighbor scale applied to the viewer image.");
DEFINE_double(arrow_length, 5,
              "Displayed optical-flow arrow length in pixels.");

DEFINE_bool(display_features, true,
            "Publish annotated feature-track images.");
DEFINE_bool(display_feature_id, false,
            "Draw feature slot identifiers.");
DEFINE_bool(display_feature_patches, false,
            "Draw warped feature-patch outlines.");
