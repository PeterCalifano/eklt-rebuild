/// @file viewer.cpp
/// @brief Implements ROS1 publication of native EKLT feature overlays.
/// @details The viewer delegates image annotation to the shared ROS-free
///          renderer and owns only asynchronous ROS1 publication.

#include "viewer.h"

#include <cstdint>
#include <exception>
#include <string>

#include <cv_bridge/cv_bridge.h>

#include "visualization/feature_track_renderer.h"
#include "flags.h"

namespace viewer
{

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
        // Replace image, tracks, statistics, and time as one coherent native
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

            // Hold the snapshot lock through rendering and message conversion
            // so ROS1 observes one coherent owning native snapshot.
            std::lock_guard<std::mutex> lock(data_mutex_);
            eklt_visualization::SFeatureTrackRenderConfig config;
            config.scale = FLAGS_scale;
            config.arrow_length = FLAGS_arrow_length;
            config.draw_patch_outlines = FLAGS_display_feature_patches;
            config.draw_feature_ids = FLAGS_display_feature_id;

            try
            {
                const std::uint64_t origin_ns = feature_track_data_.t_init.toNSec();
                const int64_t origin_t_us = static_cast<int64_t>(origin_ns / 1000U);
                eklt_visualization::SRenderedTrackImage rendered =
                    eklt_visualization::RenderFeatureTrackOverlay(feature_track_data_.snapshot,
                                                                  config,
                                                                  origin_t_us);
                cv::Mat image(rendered.height, rendered.width, CV_8UC3,
                              rendered.pixels.data(), rendered.step);
                publishImage(image, feature_track_data_.t, "bgr8", tracks_pub_);
            }
            catch (const std::exception &error)
            {
                ROS_ERROR_STREAM_THROTTLE(1.0,
                                          "Failed to render EKLT feature tracks: "
                                              << error.what());
            }
        }
    }

} // namespace viewer
