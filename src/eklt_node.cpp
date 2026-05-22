#include <ros/ros.h>
#include <gflags/gflags.h>

#include "flags.h"
#include "viewer.h"
#include "tracker.h"


int main(int argc, char** argv)
{
  google::InitGoogleLogging(argv[0]);
  google::ParseCommandLineFlags(&argc, &argv, true);
  google::InstallFailureSignalHandler();
  FLAGS_alsologtostderr = true;
  FLAGS_colorlogtostderr = true;

  ros::init(argc, argv, "eklt");
  ros::NodeHandle nh;

  viewer::Viewer viewer(nh);
  tracker::Tracker tracker(nh, viewer);

  ros::spin();


  return 0;
}
