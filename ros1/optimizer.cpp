/// @file optimizer.cpp
/// @brief Implements the ROS1 overlay optimizer adapter.
/// @details All photometric calculations and gradient-cache ownership are
///          delegated to the consolidated ROS-free implementation.

#include "optimizer.h"

#include <algorithm>
#include <exception>

#include <glog/logging.h>

#include "flags.h"
#include "patch.h"
#include "tracker_utils.h"

namespace nlls
{

    Optimizer::Optimizer()
        : optimizer_(FLAGS_max_num_iterations)
    {
    }

    void Optimizer::decrementCounter(ros::Time &time)
    {
        optimizer_.releaseGradientImageReference(tracker::RosTimeToUs(time));
    }

    void Optimizer::getLogGradients(const cv::Mat &image,
                                    cv::Mat &gradient_x,
                                    cv::Mat &gradient_y)
    {
        eklt_core::CPhotometricOptimizer::computeLogGradients(image, &gradient_x, &gradient_y,
                                                              FLAGS_log_eps);
    }

    bool Optimizer::precomputeLogImageArray(const tracker::Patches &patches,
                                            const tracker::ImageBuffer::iterator &image_it)
    {
        const int64_t timestamp_us = tracker::RosTimeToUs(image_it->first);
        const int reference_count =
            static_cast<int>(std::count_if(patches.begin(), patches.end(),
                                           [timestamp_us](const tracker::Patch &patch)
                                           {
                                               return !patch.lost &&
                                                      patch.t_init_us == timestamp_us;
                                           }));
        if (reference_count <= 0)
        {
            return false;
        }

        try
        {
            optimizer_.precomputeGradientImage(image_it->second, timestamp_us,
                                               reference_count, FLAGS_log_eps);
        }
        catch (const std::exception &exception)
        {
            LOG(ERROR) << "Failed to cache ROS1 initialization gradients: "
                       << exception.what();
            return false;
        }
        return true;
    }

    void Optimizer::optimizeParameters(const cv::Mat &event_frame,
                                       tracker::Patch &patch)
    {
        optimizer_.optimize(event_frame, &patch);
        patch.t_curr_ = tracker::RosTimeFromUs(patch.t_curr_us);
    }

} // namespace nlls
