/// @file patch.cpp
/// @brief Implements ROS1 conversion around native photometric patch state.
/// @details The adapter adds no tracking algorithm; all buffering, warping, and
///          event-frame accumulation delegate to `SPhotometricPatch`.

#include "patch.h"

#include <atomic>
#include <random>
#include <utility>

#include "flags.h"
#include "tracker_utils.h"

namespace tracker
{
    namespace
    {

        int NextPatchId()
        {
            static std::atomic<int> next_id{0};
            return next_id.fetch_add(1);
        }

        cv::Scalar MakePatchColor()
        {
            static std::uniform_real_distribution<double> distribution(0.0, 255.0);
            static std::default_random_engine engine;
            return cv::Scalar(distribution(engine),
                              distribution(engine),
                              distribution(engine));
        }

    } // namespace

    Patch::Patch(const cv::Point2d &center, const ros::Time &t_init)
        : eklt_core::SPhotometricPatch(NextPatchId(), center,
                                       RosTimeToUs(t_init),
                                       FLAGS_patch_size,
                                       FLAGS_batch_size,
                                       FLAGS_update_every_n_events),
          t_init_(t_init),
          t_curr_(t_init),
          color_(MakePatchColor())
    {
    }

    Patch::Patch()
        : Patch(cv::Point2d(-1.0, -1.0), ros::Time::now())
    {
        lost = true;
    }

    void Patch::insert(const dvs_msgs::Event &event)
    {
        // Convert only at the ROS boundary; the native event buffer remains
        // independent of ROS message ownership.
        const eklt_core::SEventSample sample{
            event.x,
            event.y,
            static_cast<int8_t>(event.polarity ? 1 : -1),
            RosTimeToUs(event.ts),
        };
        eklt_core::SPhotometricPatch::insert(sample);
    }

    bool Patch::getEventFramesAndReset(cv::Mat &event_frame)
    {
        const bool has_observation =
            eklt_core::SPhotometricPatch::getEventFrameAndReset(&event_frame);
        if (!event_frame.empty())
        {
            t_curr_ = RosTimeFromUs(t_curr_us);
        }
        return has_observation;
    }

    void Patch::reset(const cv::Point2d &init_center, const ros::Time &t)
    {
        // Replace the complete native state atomically so no event, gradient,
        // or warp from the retired feature survives slot reuse.
        eklt_core::SPhotometricPatch replacement(NextPatchId(), init_center, RosTimeToUs(t),
                                                 FLAGS_patch_size, FLAGS_batch_size,
                                                 FLAGS_update_every_n_events);
        static_cast<eklt_core::SPhotometricPatch &>(*this) =
            std::move(replacement);

        t_init_ = t;
        t_curr_ = t;
        color_ = MakePatchColor();
    }

    void Patch::warpPixel(const cv::Point2d &unwarped,
                          cv::Point2d &warped) const
    {
        eklt_core::SPhotometricPatch::warpPixel(unwarped, &warped);
    }

} // namespace tracker
