/// @file eklt_node.cpp
/// @brief Runs the legacy ROS1 EKLT tracker frontend.
/// @details Command-line gflags configure either frame-backed or event-only
///          initialization before ROS subscriptions and workers are created.

#include <gflags/gflags.h>
#include <glog/logging.h>
#include <ros/ros.h>

#include "tracker.h"
#include "viewer.h"

int main(int argc, char **argv)
{
    google::InitGoogleLogging(argv[0]);
    google::ParseCommandLineFlags(&argc, &argv, true);
    google::InstallFailureSignalHandler();
    FLAGS_alsologtostderr = true;
    FLAGS_colorlogtostderr = true;

    ros::init(argc, argv, "eklt");
    ros::NodeHandle node_handle;

    viewer::Viewer viewer(node_handle);
    tracker::Tracker tracker(node_handle, viewer);
    ros::spin();

    return 0;
}
