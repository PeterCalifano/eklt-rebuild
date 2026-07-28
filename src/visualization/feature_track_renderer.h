/// @file feature_track_renderer.h
/// @brief Declares transport-neutral rendering of EKLT feature snapshots.
/// @details Keeps display policy outside the algorithm core while converting
///          owning snapshots into contiguous `bgr8` data without ROS types,
///          GUI ownership, or retained tracker state.

#ifndef EKLT_VISUALIZATION_FEATURE_TRACK_RENDERER_H_
#define EKLT_VISUALIZATION_FEATURE_TRACK_RENDERER_H_

#include <cstdint>
#include <vector>

#include "eklt_core/tracker_orchestrator.h"

namespace eklt_visualization
{

    /// @brief Display policy for one feature-track overlay.
    struct SFeatureTrackRenderConfig
    {
        /// @brief Nearest-neighbor output scale relative to the sensor image.
        double scale{4.0};
        /// @brief Reference-space optical-flow arrow length in pixels.
        double arrow_length{5.0};
        /// @brief Draw warped patch boundaries for initialized tracks.
        bool draw_patch_outlines{false};
        /// @brief Draw stable feature identifiers beside active tracks.
        bool draw_feature_ids{false};
    };

    /// @brief Owning transport-neutral `bgr8` image.
    struct SRenderedTrackImage
    {
        /// @brief Output width in pixels.
        int width{0};
        /// @brief Output height in pixels.
        int height{0};
        /// @brief Bytes between consecutive image rows.
        int step{0};
        /// @brief Snapshot timestamp represented by the image.
        int64_t t_us{-1};
        /// @brief Contiguous row-major `bgr8` bytes.
        std::vector<uint8_t> pixels;

        /// @brief Check whether storage and metadata describe one `bgr8` image.
        /// @return True when dimensions, stride, timestamp, and byte count agree.
        bool valid() const;
    };

    /// @brief Render one owning tracker snapshot as a deterministic `bgr8` overlay.
    /// @param snapshot Current image and lightweight feature state.
    /// @param config Display scale and optional annotation policy.
    /// @param origin_t_us Timestamp used as the elapsed-time display origin.
    /// @return Owning contiguous rendered image.
    /// @throws std::invalid_argument When the snapshot, configuration, track
    ///         geometry, or timestamp relationship is invalid.
    SRenderedTrackImage RenderFeatureTrackOverlay(const eklt_core::STrackerSnapshot &snapshot,
                                                  const SFeatureTrackRenderConfig &config,
                                                  int64_t origin_t_us);

} // namespace eklt_visualization

#endif // EKLT_VISUALIZATION_FEATURE_TRACK_RENDERER_H_
