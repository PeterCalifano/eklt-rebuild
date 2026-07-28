/// @file feature_track_renderer.cpp
/// @brief Implements transport-neutral EKLT feature-track rendering.
/// @details Reuses the native snapshot and normalization contracts while
///          preserving the established ROS1 overlay appearance.

#include "visualization/feature_track_renderer.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <opencv2/imgproc.hpp>

#include "eklt_core/image_normalization.h"

namespace eklt_visualization
{
    namespace
    {

        /// @brief Convert a scalar native image to fixed-depth display storage.
        /// @param image Frame-backed or reconstructed scalar image.
        /// @return Contiguous `CV_8U` image.
        cv::Mat MakeDisplayMono8(const cv::Mat &image)
        {
            const cv::Mat normalized =
                eklt_core::NormalizeImageToUnitRange64(image);
            if (normalized.empty())
            {
                throw std::invalid_argument("feature renderer requires one scalar image");
            }

            cv::Mat mono_image;
            normalized.convertTo(mono_image, CV_8U, 255.0);
            return mono_image;
        }

        /// @brief Derive a stable display color from a native track identifier.
        /// @param id Stable native track identifier.
        /// @return Deterministic BGR drawing color.
        cv::Scalar TrackColor(int id)
        {
            const std::uint32_t hash =
                static_cast<std::uint32_t>(id) * 2654435761U + 2246822519U;
            return cv::Scalar(64U + (hash & 0x7FU),
                              64U + ((hash >> 8U) & 0x7FU),
                              64U + ((hash >> 16U) & 0x7FU));
        }

        /// @brief Check whether one point has finite image coordinates.
        /// @param point Point to inspect.
        /// @return True when both coordinates are finite.
        bool IsFinitePoint(const cv::Point2d &point)
        {
            return std::isfinite(point.x) && std::isfinite(point.y);
        }

        /// @brief Reject active feature state that OpenCV cannot render safely.
        /// @param track Lightweight track state to validate.
        void ValidateTrack(const eklt_core::STrackState &track)
        {
            if (!IsFinitePoint(track.init_center) || !IsFinitePoint(track.center) ||
                !std::isfinite(track.flow_angle) || track.half_size < 0)
            {
                throw std::invalid_argument("feature renderer received invalid track geometry");
            }

            for (int row = 0; row < 3; ++row)
            {
                for (int column = 0; column < 3; ++column)
                {
                    if (!std::isfinite(track.warping(row, column)))
                    {
                        throw std::invalid_argument(
                            "feature renderer received a non-finite track warp");
                    }
                }
            }
        }

        /// @brief Convert one scaled point to the integer OpenCV drawing domain.
        /// @param point Source image point.
        /// @param scale Output image scale.
        /// @return Scaled integer drawing coordinate.
        cv::Point ScalePoint(const cv::Point2d &point, double scale)
        {
            const double scaled_x = scale * point.x;
            const double scaled_y = scale * point.y;
            const double minimum_safe_coordinate =
                static_cast<double>(std::numeric_limits<int>::min()) + 0.5;
            const double maximum_safe_coordinate =
                static_cast<double>(std::numeric_limits<int>::max()) - 0.5;
            if (!std::isfinite(scaled_x) || !std::isfinite(scaled_y) ||
                scaled_x < minimum_safe_coordinate ||
                scaled_x > maximum_safe_coordinate ||
                scaled_y < minimum_safe_coordinate ||
                scaled_y > maximum_safe_coordinate)
            {
                throw std::invalid_argument(
                    "feature renderer coordinate exceeds the drawing range");
            }
            return cv::Point(cvRound(scaled_x), cvRound(scaled_y));
        }

    } // namespace

    bool SRenderedTrackImage::valid() const
    {
        if (width <= 0 || height <= 0 ||
            width > std::numeric_limits<int>::max() / 3 ||
            step != width * 3 || t_us < 0)
        {
            return false;
        }

        const std::size_t expected_size =
            static_cast<std::size_t>(step) * static_cast<std::size_t>(height);
        return pixels.size() == expected_size;
    }

    SRenderedTrackImage RenderFeatureTrackOverlay(const eklt_core::STrackerSnapshot &snapshot,
                                                  const SFeatureTrackRenderConfig &config,
                                                  int64_t origin_t_us)
    {
        if (!snapshot.valid() || snapshot.t_us < 0 || origin_t_us < 0 ||
            origin_t_us > snapshot.t_us)
        {
            throw std::invalid_argument("feature renderer requires a valid timestamped snapshot");
        }
        if (!std::isfinite(config.scale) || config.scale <= 0.0 ||
            !std::isfinite(config.arrow_length) || config.arrow_length < 0.0)
        {
            throw std::invalid_argument("feature renderer configuration is invalid");
        }

        // Derive bounded integer output geometry before allocating the rendered
        // image so extreme scales cannot overflow OpenCV dimensions.
        const double scaled_width = config.scale * static_cast<double>(snapshot.image.width);
        const double scaled_height = config.scale * static_cast<double>(snapshot.image.height);
        if (!std::isfinite(scaled_width) || !std::isfinite(scaled_height) ||
            scaled_width < 1.0 || scaled_height < 1.0 ||
            scaled_width >
                static_cast<double>(std::numeric_limits<int>::max() / 3) ||
            scaled_height > static_cast<double>(std::numeric_limits<int>::max()))
        {
            throw std::invalid_argument("feature renderer output geometry is invalid");
        }

        // Normalize either initialization path, convert to color, and preserve
        // the established nearest-neighbor feature-display scale.
        const cv::Mat mono_image = MakeDisplayMono8(snapshot.image.image);
        cv::Mat color_image;
        cv::cvtColor(mono_image, color_image, cv::COLOR_GRAY2BGR);

        cv::Mat rendered;
        const cv::Size output_size(static_cast<int>(scaled_width),
                                   static_cast<int>(scaled_height));
        cv::resize(color_image, rendered, output_size, 0.0, 0.0, cv::INTER_NEAREST);

        const double elapsed_s =
            static_cast<double>(snapshot.t_us - origin_t_us) / 1000000.0;
        std::ostringstream time_stream;
        time_stream << "t = " << std::fixed << std::setprecision(6) << elapsed_s;
        const cv::Point time_position =
            ScalePoint(cv::Point2d(snapshot.image.width - 140,
                                   snapshot.image.height - 2),
                       config.scale);
        cv::putText(rendered, time_stream.str(), time_position,
                    cv::FONT_HERSHEY_COMPLEX_SMALL, config.scale * 0.7,
                    cv::Scalar(0, 255, 255), 1, cv::LINE_AA);

        for (const eklt_core::STrackState &track : snapshot.tracks)
        {
            if (track.lost)
            {
                continue;
            }
            ValidateTrack(track);

            const cv::Scalar color = TrackColor(track.id);
            const cv::Point center = ScalePoint(track.center, config.scale);
            cv::drawMarker(rendered, center, color, cv::MARKER_CROSS, 10, 1);

            // Apply the same inverse native warp used by optimization and the
            // original viewer to construct the displayed flow direction.
            const cv::Point2d reference_arrow_tip =
                track.init_center +
                config.arrow_length *
                    cv::Point2d(std::cos(track.flow_angle), std::sin(track.flow_angle));
            cv::Point2d warped_arrow_tip;
            track.warpPixel(reference_arrow_tip, &warped_arrow_tip);
            if (!IsFinitePoint(warped_arrow_tip))
            {
                throw std::invalid_argument("feature renderer produced a non-finite flow arrow");
            }
            cv::arrowedLine(rendered, center, ScalePoint(warped_arrow_tip, config.scale),
                            cv::Scalar(255, 255, 0), 1, 8, 0, 0.1);

            const double half_size = static_cast<double>(track.half_size);
            const cv::Point2d top_left =
                track.init_center + cv::Point2d(-half_size, -half_size);
            const cv::Point2d top_right =
                track.init_center + cv::Point2d(half_size, -half_size);
            const cv::Point2d bottom_left =
                track.init_center + cv::Point2d(-half_size, half_size);
            const cv::Point2d bottom_right =
                track.init_center + cv::Point2d(half_size, half_size);
            const cv::Point2d top_middle = (top_left + top_right) / 2.0;

            cv::Point2d top_left_warped;
            cv::Point2d top_right_warped;
            cv::Point2d bottom_left_warped;
            cv::Point2d bottom_right_warped;
            cv::Point2d top_middle_warped;
            track.warpPixel(top_left, &top_left_warped);
            track.warpPixel(top_right, &top_right_warped);
            track.warpPixel(bottom_left, &bottom_left_warped);
            track.warpPixel(bottom_right, &bottom_right_warped);
            track.warpPixel(top_middle, &top_middle_warped);

            if (!IsFinitePoint(top_left_warped) || !IsFinitePoint(top_right_warped) ||
                !IsFinitePoint(bottom_left_warped) ||
                !IsFinitePoint(bottom_right_warped) ||
                !IsFinitePoint(top_middle_warped))
            {
                throw std::invalid_argument(
                    "feature renderer produced non-finite patch geometry");
            }

            if (track.initialized && config.draw_patch_outlines)
            {
                const std::vector<cv::Point> corners = {
                    ScalePoint(top_left_warped, config.scale),
                    ScalePoint(top_right_warped, config.scale),
                    ScalePoint(bottom_right_warped, config.scale),
                    ScalePoint(bottom_left_warped, config.scale),
                };
                cv::polylines(rendered, corners, true, color, 2);
                cv::line(rendered, center, ScalePoint(top_middle_warped, config.scale),
                         color, 2);
            }

            if (config.draw_feature_ids)
            {
                const cv::Point2d text_position(track.center.x - half_size + 2.0,
                                                track.center.y - half_size + 8.0);
                cv::putText(rendered, std::to_string(track.id),
                            ScalePoint(text_position, config.scale),
                            cv::FONT_HERSHEY_COMPLEX_SMALL, config.scale * 0.4,
                            cv::Scalar(255, 0, 0), 2, cv::LINE_AA);
            }
        }

        // Return an owning contiguous byte vector so transport adapters and
        // generated wrappers never depend on OpenCV view lifetimes.
        if (!rendered.isContinuous())
        {
            rendered = rendered.clone();
        }
        SRenderedTrackImage output;
        output.width = rendered.cols;
        output.height = rendered.rows;
        output.step = rendered.cols * rendered.channels();
        output.t_us = snapshot.t_us;
        output.pixels.assign(rendered.datastart, rendered.dataend);
        return output;
    }

} // namespace eklt_visualization
