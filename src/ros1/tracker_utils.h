/// @file tracker_utils.h
/// @brief Declares deterministic ROS1 event and timestamp helpers.
/// @details Implementations are compiled with the ROS1 target so public headers
///          no longer carry substantial inline behavior.

#pragma once

#include <cstdint>

#include <dvs_msgs/Event.h>
#include <ros/ros.h>

#include "types.h"

namespace tracker
{

    /// @brief Convert a nonnegative ROS timestamp to integer microseconds.
    /// @param timestamp ROS timestamp to convert.
    /// @return Timestamp truncated to microsecond precision.
    int64_t RosTimeToUs(const ros::Time &timestamp);

    /// @brief Convert a nonnegative microsecond timestamp to ROS time.
    /// @param timestamp_us Timestamp in microseconds.
    /// @return Equivalent ROS timestamp.
    /// @throws std::invalid_argument If `timestamp_us` is outside the
    ///         nonnegative ROS1 time range.
    ros::Time RosTimeFromUs(int64_t timestamp_us);

    /// @brief Insert one event while preserving ascending timestamp order.
    /// @param events_buffer Mutable tracker event buffer.
    /// @param event Event to insert.
    void InsertEventInSortedOrder(EventBuffer &events_buffer,
                                  const dvs_msgs::Event &event);

    /// @brief Advance to the newest frame strictly before a timestamp.
    /// @param images Timestamp-indexed image buffer.
    /// @param timestamp Target event timestamp.
    /// @param current_image_it Iterator updated when a newer valid image exists.
    /// @return True when `current_image_it` advanced.
    bool AdvanceToFirstImageBeforeTimestamp(ImageBuffer &images,
                                            const ros::Time &timestamp,
                                            ImageBuffer::iterator &current_image_it);

} // namespace tracker
