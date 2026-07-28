/// @file tracker_utils.cpp
/// @brief Implements deterministic ROS1 overlay event and timestamp helpers.
/// @details Integer conversion avoids floating-point drift at the native
///          microsecond boundary used by reconstruction and photometric caches.

#include "tracker_utils.h"

#include <limits>
#include <stdexcept>

namespace tracker
{

    int64_t RosTimeToUs(const ros::Time &timestamp)
    {
        // ROS1 time stores nonnegative seconds and nanoseconds separately, so
        // integer composition preserves every complete microsecond exactly.
        return static_cast<int64_t>(timestamp.sec) * 1000000LL +
               static_cast<int64_t>(timestamp.nsec / 1000U);
    }

    ros::Time RosTimeFromUs(int64_t timestamp_us)
    {
        constexpr int64_t kMaximumRosTimestampUs =
            static_cast<int64_t>(std::numeric_limits<uint32_t>::max()) * 1000000LL + 999999LL;
        if (timestamp_us < 0 || timestamp_us > kMaximumRosTimestampUs)
        {
            throw std::invalid_argument("native timestamp lies outside the ROS1 time range");
        }

        // Reconstruct ROS time at the same microsecond precision owned by the
        // native tracker.
        ros::Time timestamp;
        timestamp.fromNSec(static_cast<uint64_t>(timestamp_us) * 1000ULL);
        return timestamp;
    }

    void InsertEventInSortedOrder(EventBuffer &events_buffer,
                                  const dvs_msgs::Event &event)
    {
        // Preserve the arrival order of equal timestamps while shifting only
        // strictly newer events behind the inserted sample.
        events_buffer.push_back(event);
        int index = static_cast<int>(events_buffer.size()) - 2;
        while (index >= 0 &&
               events_buffer[static_cast<std::size_t>(index)].ts > event.ts)
        {
            events_buffer[static_cast<std::size_t>(index + 1)] =
                events_buffer[static_cast<std::size_t>(index)];
            --index;
        }
        events_buffer[static_cast<std::size_t>(index + 1)] = event;
    }

    bool AdvanceToFirstImageBeforeTimestamp(ImageBuffer &images,
                                            const ros::Time &timestamp,
                                            ImageBuffer::iterator &current_image_it)
    {
        if (images.empty() || current_image_it == images.end())
        {
            return false;
        }

        // Advance without crossing the target timestamp; this preserves the
        // latest-causal frame policy used by both initialization modes.
        bool advanced = false;
        ImageBuffer::iterator next_image_it = current_image_it;
        while (next_image_it->first < timestamp)
        {
            ++next_image_it;
            if (next_image_it == images.end())
            {
                break;
            }
            if (next_image_it->first < timestamp)
            {
                current_image_it = next_image_it;
                advanced = true;
            }
        }
        return advanced;
    }

} // namespace tracker
