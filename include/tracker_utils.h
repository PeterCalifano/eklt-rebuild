#pragma once

#include "types.h"

namespace tracker
{

    /**
     * @brief Insert one event while preserving ascending timestamp order.
     * @param eventsBuffer Mutable tracker event buffer.
     * @param event Event to insert.
     *
     * EKLT normally receives almost-sorted event streams. Insertion sort keeps
     * the common path cheap while still giving deterministic behavior when rare
     * out-of-order events arrive.
     */
    inline void InsertEventInSortedOrder(EventBuffer &eventsBuffer, const dvs_msgs::Event &event)
    {
        eventsBuffer.push_back(event);

        int j = static_cast<int>(eventsBuffer.size()) - 2;
        while (j >= 0 && eventsBuffer[j].ts > event.ts)
        {
            eventsBuffer[j + 1] = eventsBuffer[j];
            --j;
        }
        eventsBuffer[j + 1] = event;
    }

    /**
     * @brief Move an image iterator to the newest frame strictly before a timestamp.
     * @param images Timestamp-indexed image buffer.
     * @param timestamp Target event timestamp.
     * @param current_image_it Iterator updated in-place when a newer valid image exists.
     * @return True when @p current_image_it advanced to a newer image.
     *
     * This preserves the tracker policy that events are processed against the
     * latest image whose timestamp is lower than the current event timestamp.
     */
    inline bool AdvanceToFirstImageBeforeTimestamp(ImageBuffer &images,
                                                   const ros::Time &timestamp,
                                                   ImageBuffer::iterator &current_image_it)
    {
        bool next_image = false;
        auto next_image_it = current_image_it;

        while (next_image_it->first < timestamp)
        {
            ++next_image_it;
            if (next_image_it == images.end())
            {
                break;
            }

            if (next_image_it->first < timestamp)
            {
                next_image = true;
                current_image_it = next_image_it;
            }
        }

        return next_image;
    }

} // namespace tracker
