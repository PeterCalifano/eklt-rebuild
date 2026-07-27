/// @file viewer.cpp
/// @brief Implements ROS1 publication of native EKLT snapshots.
/// @details Floating-point FIBAR images are normalized for display while the
///          viewer remains a transport-only `feature_tracks` image publisher.

#include "viewer.h"

#include <cmath>
#include <cstdint>
#include <vector>

#include <cv_bridge/cv_bridge.h>
#include <opencv2/imgproc.hpp>

#include "eklt_core/image_normalization.h"
#include "flags.h"

namespace viewer
{
    namespace
    {

        /// @brief Convert one native image into the advertised display depth.
        /// @param image Scalar frame-backed or reconstructed image.
        /// @return Eight-bit display image, or empty for invalid storage.
        cv::Mat MakeDisplayMono8(const cv::Mat &image)
        {
            if (image.empty() || image.channels() != 1)
            {
                return cv::Mat();
            }
            if (image.depth() == CV_8U)
            {
                return image;
            }

            // Apply the native finite normalization policy only to the display
            // copy; the orchestrator snapshot retains its original precision.
            const cv::Mat normalized = eklt_core::NormalizeImageToUnitRange64(image);
            cv::Mat display;
            normalized.convertTo(display, CV_8U, 255.0);
            return display;
        }

        /// @brief Derive a stable display color from a native track identifier.
        /// @param id Stable native track identifier.
        /// @return Deterministic BGR drawing color.
        cv::Scalar TrackColor(int id)
        {
            const std::uint32_t hash = static_cast<std::uint32_t>(id) * 2654435761U + 2246822519U;
            return cv::Scalar(64U + (hash & 0x7FU), 64U + ((hash >> 8U) & 0x7FU),
                              64U + ((hash >> 16U) & 0x7FU));
        }

    } // namespace

    Viewer::Viewer(ros::NodeHandle &nh)
        : nh_(nh), it_(nh), stop_requested_(false), got_first_image_(false)
    {
    }

    Viewer::~Viewer()
    {
        stop_requested_.store(true);
        if (display_thread_.joinable())
        {
            display_thread_.join();
        }
        tracks_pub_.shutdown();
    }

    void Viewer::setViewData(const eklt_core::STrackerSnapshot &snapshot,
                             const ros::Time &timestamp)
    {
        // Replace image, patches, statistics, and time as one coherent native
        // snapshot so the publishing worker never combines different updates.
        std::lock_guard<std::mutex> lock(data_mutex_);
        feature_track_data_.snapshot = snapshot;
        feature_track_data_.t = timestamp;
        got_first_image_.store(true);
    }

    void Viewer::initViewData(const ros::Time &timestamp)
    {
        tracks_pub_ = it_.advertise("feature_tracks", 1);

        // Preserve the established asynchronous ROS publisher while starting
        // at most one worker for the complete tracker lifetime.
        if (!display_thread_.joinable())
        {
            display_thread_ = std::thread(&Viewer::displayTracks, this);
        }

        std::lock_guard<std::mutex> lock(data_mutex_);
        feature_track_data_.t = timestamp;
        feature_track_data_.t_init = timestamp;
    }

    void Viewer::publishImage(const cv::Mat &image, const ros::Time &stamp,
                              const std::string &encoding,
                              const image_transport::Publisher &publisher)
    {
        cv_bridge::CvImage cv_image;
        cv_image.encoding = encoding;
        cv_image.image = image;
        cv_image.header.stamp = stamp;
        publisher.publish(cv_image.toImageMsg());
    }

    void Viewer::displayTracks()
    {
        ros::Rate rate(30);
        while (ros::ok() && !stop_requested_.load())
        {
            rate.sleep();
            if (!got_first_image_.load() || !FLAGS_display_features)
            {
                continue;
            }

            // Hold the snapshot lock across rendering so the image and native
            // patch vector remain stable through message construction.
            std::lock_guard<std::mutex> lock(data_mutex_);
            const cv::Mat &image = feature_track_data_.snapshot.image.image;
            drawOnImage(feature_track_data_, feature_track_view_, image);
            if (!feature_track_view_.empty())
            {
                publishImage(feature_track_view_, feature_track_data_.t, "bgr8", tracks_pub_);
            }
        }
    }

    void Viewer::drawOnImage(const FeatureTrackData &data, cv::Mat &view, const cv::Mat &image)
    {
        const cv::Mat mono_image = MakeDisplayMono8(image);
        if (mono_image.empty())
        {
            view.release();
            return;
        }

        const double scale = FLAGS_scale;
        const double arrow_length = FLAGS_arrow_length;

        // Convert both initialization modes to `bgr8` before applying the
        // established nearest-neighbor scale and drawing native patch state.
        cv::Mat color_image;
        cv::cvtColor(mono_image, color_image, cv::COLOR_GRAY2BGR);
        const cv::Size output_size(static_cast<int>(scale * color_image.cols),
                                   static_cast<int>(scale * color_image.rows));
        cv::resize(color_image, view, output_size, 0.0, 0.0, cv::INTER_NEAREST);

        const std::string time_string =
            "t = " + std::to_string(data.t.toSec() - data.t_init.toSec());
        cv::putText(view, time_string,
                    scale * (cv::Point(image.cols, image.rows) - cv::Point(140, 2)),
                    cv::FONT_HERSHEY_COMPLEX_SMALL, scale * 0.7,
                    cv::Scalar(0, 255, 255), 1, cv::LINE_AA);

        for (const eklt_core::STrackState &track : data.snapshot.tracks)
        {
            if (track.lost)
            {
                continue;
            }

            const cv::Scalar color = TrackColor(track.id);
            cv::drawMarker(view, scale * track.center, color, cv::MARKER_CROSS, 10, 1);

            // Draw the flow direction through the same native inverse warp
            // used by optimization and wrapper snapshots.
            const cv::Point2d flow_arrow_tip =
                track.init_center +
                arrow_length * cv::Point2d(std::cos(track.flow_angle), std::sin(track.flow_angle));
            cv::Point2d warped_flow_arrow_tip;
            track.warpPixel(flow_arrow_tip, &warped_flow_arrow_tip);
            cv::arrowedLine(view, scale * track.center, scale * warped_flow_arrow_tip,
                            cv::Scalar(255, 255, 0), 1, 8, 0, 0.1);

            const int half_size = track.half_size;
            const cv::Point2d top_left(track.init_center.x - half_size,
                                       track.init_center.y - half_size);
            const cv::Point2d top_right(track.init_center.x + half_size,
                                        track.init_center.y - half_size);
            const cv::Point2d bottom_left(track.init_center.x - half_size,
                                          track.init_center.y + half_size);
            const cv::Point2d bottom_right(track.init_center.x + half_size,
                                           track.init_center.y + half_size);
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

            const std::vector<cv::Point> corners = {
                scale * top_left_warped,
                scale * top_right_warped,
                scale * bottom_right_warped,
                scale * bottom_left_warped,
            };
            if (track.initialized && FLAGS_display_feature_patches)
            {
                cv::polylines(view, corners, true, color, 2);
                cv::line(view, scale * track.center, scale * top_middle_warped, color, 2);
            }

            if (FLAGS_display_feature_id)
            {
                const cv::Point text_position(static_cast<int>(track.center.x) - half_size + 2,
                                              static_cast<int>(track.center.y) - half_size + 8);
                cv::putText(view, std::to_string(track.id), scale * text_position,
                            cv::FONT_HERSHEY_COMPLEX_SMALL, scale * 0.4, cv::Scalar(255, 0, 0), 2,
                            cv::LINE_AA);
            }
        }
    }

} // namespace viewer
