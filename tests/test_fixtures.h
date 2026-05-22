#pragma once

#include <dvs_msgs/Event.h>
#include <ros/ros.h>

namespace fixtures
{

inline dvs_msgs::Event MakeEvent(const uint16_t x,
                                 const uint16_t y,
                                 const double timestamp_sec,
                                 const bool polarity)
{
    dvs_msgs::Event event;
    event.x = x;
    event.y = y;
    event.ts = ros::Time(timestamp_sec);
    event.polarity = polarity;
    return event;
}

} // namespace fixtures
