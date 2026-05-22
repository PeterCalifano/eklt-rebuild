#pragma once

#include "types.h"

namespace tracker
{

    inline void InsertEventInSortedOrder(EventBuffer &eventsBuffer, const dvs_msgs::Event &event)
    {
        eventsBuffer.push_back(event);

        int j = static_cast<int>(eventsBuffer.size()) - 2;
        // TODO optimize sorting replacing loop? 
        // From Claude: This is already near-optimal when events arrive near-sorted (typical DVS case): inner loop exits fast, ~O(1) per insert. Binary-search version pays log n comparisons even in best case. Net win only if out-of-order spans are large. For mostly-sorted streams, current code may be faster.

        while (j >= 0 && eventsBuffer[j].ts > event.ts)
        {
            eventsBuffer[j + 1] = eventsBuffer[j];
            --j;
        }
        eventsBuffer[j + 1] = event;
    }

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
