#pragma once

#include <gflags/gflags.h>

// feature detection
DECLARE_int32(max_corners);
DECLARE_int32(min_corners);
DECLARE_int32(min_distance);
DECLARE_int32(block_size);

DECLARE_double(k);
DECLARE_double(quality_level);
DECLARE_double(log_eps);
DECLARE_double(first_image_t);
DECLARE_string(tracks_file_txt);

// tracker
DECLARE_int32(lk_window_size);
DECLARE_int32(num_pyramidal_layers);
DECLARE_int32(batch_size);
DECLARE_int32(patch_size);
DECLARE_int32(max_num_iterations);

DECLARE_double(displacement_px);
DECLARE_double(tracking_quality);
DECLARE_string(bootstrap);

// viewer
DECLARE_int32(update_every_n_events);
DECLARE_double(scale);
DECLARE_double(arrow_length);

DECLARE_bool(display_features);
DECLARE_bool(display_feature_id);
DECLARE_bool(display_feature_patches);
