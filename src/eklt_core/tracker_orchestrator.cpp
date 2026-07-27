/// @file tracker_orchestrator.cpp
/// @brief Implements the complete ROS-free EKLT tracking state machine.
/// @details All reusable scheduling and feature-lifecycle behavior lives here;
///          middleware adapters only convert inputs and publish returned state.

#include "eklt_core/tracker_orchestrator.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

#include <opencv2/video/tracking.hpp>

#include "eklt_core/image_normalization.h"
#include "event_recon_fibar_core/fibar_reconstructor.h"

namespace eklt_core
{
    namespace
    {

        constexpr const char *kEventCameraFrame = "event_camera";

        uint64_t SaturatingAdd(uint64_t value, std::size_t increment)
        {
            const uint64_t maximum = std::numeric_limits<uint64_t>::max();
            if (increment > maximum - value)
            {
                return maximum;
            }
            return value + static_cast<uint64_t>(increment);
        }

        cv::Mat PrepareKltImage(const cv::Mat &image)
        {
            if (image.empty() || image.dims != 2 || image.channels() != 1)
            {
                return cv::Mat();
            }
            if (image.depth() == CV_8U)
            {
                return image;
            }

            // KLT consumes eight-bit scalar images. Reconstructed frames use
            // the same finite normalization as all native image providers.
            const cv::Mat normalized = NormalizeImageToUnitRange64(image);
            cv::Mat klt_image;
            normalized.convertTo(klt_image, CV_8U, 255.0);
            return klt_image;
        }

        SImageFrame CloneFrame(const SImageFrame &frame)
        {
            SImageFrame copy = frame;
            copy.image = frame.image.clone();

            // The provider field is non-owning, so snapshots use static storage
            // instead of retaining a potentially transient caller pointer.
            copy.frame_id = kEventCameraFrame;
            return copy;
        }

        STrackState MakeTrackState(const SPhotometricPatch &patch)
        {
            STrackState track;
            track.id = patch.id;
            track.init_center = patch.init_center;
            track.center = patch.center;
            track.t_init_us = patch.t_init_us;
            track.t_curr_us = patch.t_curr_us;
            track.half_size = patch.half_size;
            track.flow_angle = patch.flow_angle;
            track.tracking_quality = patch.tracking_quality;
            track.initialized = patch.initialized;
            track.lost = patch.lost;

            // Retired sentinel slots have no mutable warp allocation. Keep the
            // lightweight snapshot identity transform for those slots.
            if (patch.warping.rows != 3 || patch.warping.cols != 3 ||
                patch.warping.type() != CV_64F)
            {
                return track;
            }

            for (int row = 0; row < 3; ++row)
            {
                for (int column = 0; column < 3; ++column)
                {
                    track.warping(row, column) = patch.warping.at<double>(row, column);
                }
            }
            return track;
        }

    } // namespace

    bool STrackerSnapshot::valid() const
    {
        return image.valid();
    }

    void STrackState::warpPixel(const cv::Point2d &unwarped, cv::Point2d *warped) const
    {
        if (warped == nullptr)
        {
            return;
        }

        const cv::Matx33d inverse_warp = warping.inv();
        warped->x =
            inverse_warp(0, 0) * unwarped.x + inverse_warp(0, 1) * unwarped.y + inverse_warp(0, 2);
        warped->y =
            inverse_warp(1, 0) * unwarped.x + inverse_warp(1, 1) * unwarped.y + inverse_warp(1, 2);
    }

    CEkltTrackerOrchestrator::CEkltTrackerOrchestrator(const SEkltTrackerConfig &config)
        : config_(config), current_image_it_(images_.end()),
          optimizer_(std::max(1, config.max_num_iterations))
    {
        validateConfig();
        if (config_.initialization_mode == ETrackerInitializationMode::EventOnlyFibar)
        {
            event_recon_fibar_core::SFibarConfig fibar_config;
            fibar_config.width = config_.width;
            fibar_config.height = config_.height;
            fibar_config.cutoff_time_us = config_.fibar_cutoff_time_us;
            fibar_config.fill_ratio = config_.fibar_fill_ratio;
            fibar_config.use_spatial_filter = config_.fibar_use_spatial_filter;
            fibar_reconstructor_ =
                std::make_unique<event_recon_fibar_core::CFibarReconstructor>(fibar_config);
        }
    }

    CEkltTrackerOrchestrator::~CEkltTrackerOrchestrator() = default;

    void CEkltTrackerOrchestrator::validateConfig() const
    {
        if (config_.width <= 0 || config_.height <= 0)
        {
            throw std::invalid_argument("tracker sensor geometry must be positive");
        }
        if (config_.first_image_t_us < -1)
        {
            throw std::invalid_argument("tracker first image timestamp must be -1 or nonnegative");
        }
        if (config_.max_corners <= 0 || config_.min_corners < 0 ||
            config_.min_corners > config_.max_corners)
        {
            throw std::invalid_argument("tracker feature-count limits are inconsistent");
        }
        const int minimum_dimension = std::min(config_.width, config_.height);
        if (!std::isfinite(config_.min_distance) || config_.min_distance < 0.0 ||
            !std::isfinite(config_.quality_level) || config_.quality_level <= 0.0 ||
            config_.quality_level > 1.0 || config_.block_size <= 0 ||
            config_.block_size > minimum_dimension ||
            !std::isfinite(config_.harris_k))
        {
            throw std::invalid_argument("tracker Harris configuration is invalid");
        }
        if (config_.patch_size <= 0 || config_.patch_size % 2 == 0 || config_.batch_size <= 1 ||
            config_.patch_size > minimum_dimension || config_.update_every_n_events <= 0 ||
            config_.max_num_iterations <= 0)
        {
            throw std::invalid_argument("tracker patch and optimizer configuration is invalid");
        }
        if (config_.lk_window_size <= 0 || config_.num_pyramidal_layers < 0 ||
            !std::isfinite(config_.lk_max_error) || config_.lk_max_error < 0.0)
        {
            throw std::invalid_argument("tracker KLT configuration is invalid");
        }
        if (!std::isfinite(config_.displacement_px) || config_.displacement_px <= 0.0 ||
            !std::isfinite(config_.tracking_quality) || config_.tracking_quality < 0.0 ||
            config_.tracking_quality > 1.0 || !std::isfinite(config_.log_eps) ||
            config_.log_eps <= 0.0)
        {
            throw std::invalid_argument("tracker photometric configuration is invalid");
        }
        if (config_.reconstruction_interval_events <= 0 || config_.fibar_cutoff_time_us == 0 ||
            !std::isfinite(config_.fibar_fill_ratio) || config_.fibar_fill_ratio <= 0.0 ||
            config_.fibar_fill_ratio > 1.0)
        {
            throw std::invalid_argument("tracker FIBAR configuration is invalid");
        }
    }

    void CEkltTrackerOrchestrator::reset()
    {
        images_.clear();
        current_image_it_ = images_.end();
        patches_.clear();
        lost_indices_.clear();
        track_samples_.clear();
        optimizer_ = CPhotometricOptimizer(config_.max_num_iterations);
        statistics_ = STrackerStatistics();
        next_track_id_ = 0;
        most_current_t_us_ = -1;
        events_since_reconstruction_ = 0;
        last_accepted_event_t_us_ = -1;
        initialized_ = false;

        if (fibar_reconstructor_)
        {
            fibar_reconstructor_->reset();
        }
    }

    bool CEkltTrackerOrchestrator::acceptFrame(const SImageFrame &frame)
    {
        if (config_.initialization_mode != ETrackerInitializationMode::FrameBacked)
        {
            return false;
        }
        if (!frame.valid() || frame.width != config_.width || frame.height != config_.height ||
            frame.t_us < 0)
        {
            throw std::invalid_argument("tracker frame violates storage or geometry contract");
        }
        if (frame.t_us < config_.first_image_t_us)
        {
            return false;
        }
        if (initialized_ && frame.t_us <= most_current_t_us_)
        {
            return false;
        }

        // Clone at the native boundary so caller-owned transport storage can be
        // reused immediately after this synchronous call returns.
        const std::pair<TImageBuffer::iterator, bool> insertion =
            images_.emplace(frame.t_us, CloneFrame(frame));
        if (!insertion.second)
        {
            return false;
        }
        if (!initialized_)
        {
            initializeFromFirstImage();
        }
        return true;
    }

    void CEkltTrackerOrchestrator::validateEvents(const std::vector<SEventSample> &events) const
    {
        for (const SEventSample &event : events)
        {
            if (static_cast<int>(event.x) >= config_.width ||
                static_cast<int>(event.y) >= config_.height)
            {
                throw std::out_of_range("tracker event lies outside sensor geometry");
            }
            if (event.p != -1 && event.p != 1)
            {
                throw std::invalid_argument("tracker event polarity must be -1 or +1");
            }
            if (event.t_us < 0)
            {
                throw std::invalid_argument("tracker event timestamp cannot be negative");
            }
        }
    }

    bool CEkltTrackerOrchestrator::acceptEvents(std::vector<SEventSample> events)
    {
        if (events.empty())
        {
            return true;
        }

        // Validate before mutating reconstruction or feature state, then
        // preserve source order among equal timestamps.
        validateEvents(events);
        std::stable_sort(events.begin(), events.end(),
                         [](const SEventSample &lhs, const SEventSample &rhs)
                         { return lhs.t_us < rhs.t_us; });
        if (last_accepted_event_t_us_ >= 0 && events.front().t_us < last_accepted_event_t_us_)
        {
            throw std::invalid_argument("tracker event batch regresses across native calls");
        }

        const bool can_process_events = initialized_;
        if (config_.initialization_mode == ETrackerInitializationMode::FrameBacked)
        {
            if (!initialized_)
            {
                return false;
            }
        }
        else
        {
            reconstructEventOnlyImage(events);
        }

        statistics_.accepted_events = SaturatingAdd(statistics_.accepted_events, events.size());
        last_accepted_event_t_us_ = events.back().t_us;

        // Events used to create the first causal image predate its new
        // patches. Retaining them would grow memory before initialization and
        // would incorrectly replay obsolete evidence into those patches.
        if (!initialized_ && !images_.empty())
        {
            initializeFromFirstImage();
        }
        if (!can_process_events)
        {
            return true;
        }

        for (const SEventSample &event : events)
        {
            processEvent(event);
            statistics_.processed_events = SaturatingAdd(statistics_.processed_events, 1U);
        }
        return true;
    }

    void CEkltTrackerOrchestrator::reconstructEventOnlyImage(
        const std::vector<SEventSample> &events)
    {
        if (!fibar_reconstructor_)
        {
            throw std::runtime_error("event-only tracker has no FIBAR state");
        }

        std::vector<uint16_t> x;
        std::vector<uint16_t> y;
        std::vector<int8_t> polarity;
        std::vector<int64_t> timestamps_us;
        x.reserve(events.size());
        y.reserve(events.size());
        polarity.reserve(events.size());
        timestamps_us.reserve(events.size());
        for (const SEventSample &event : events)
        {
            x.push_back(event.x);
            y.push_back(event.y);
            polarity.push_back(event.p);
            timestamps_us.push_back(event.t_us);
        }

        const event_recon_fibar_core::SEventBatchView batch{
            x.data(),
            y.data(),
            polarity.data(),
            timestamps_us.data(),
            timestamps_us.size(),
            config_.width,
            config_.height,
        };
        fibar_reconstructor_->acceptEvents(batch);

        const std::size_t available =
            std::numeric_limits<std::size_t>::max() - events_since_reconstruction_;
        events_since_reconstruction_ += std::min(available, events.size());
        const int64_t latest_t_us = timestamps_us.back();
        if ((initialized_ &&
             events_since_reconstruction_ <
                 static_cast<std::size_t>(config_.reconstruction_interval_events)) ||
            latest_t_us < config_.first_image_t_us ||
            !fibar_reconstructor_->hasImageFor(latest_t_us))
        {
            return;
        }

        const event_recon_fibar_core::SReconstructedImageView reconstruction =
            fibar_reconstructor_->requestImage(latest_t_us);
        SImageFrame frame;
        frame.image.create(reconstruction.height, reconstruction.width, CV_32F);
        fibar_reconstructor_->copyImageTo(frame.image.ptr<float>(), reconstruction.size);
        frame.t_us = reconstruction.t_us;
        frame.width = reconstruction.width;
        frame.height = reconstruction.height;
        frame.frame_id = kEventCameraFrame;

        const std::pair<TImageBuffer::iterator, bool> insertion =
            images_.emplace(frame.t_us, std::move(frame));
        if (insertion.second)
        {
            events_since_reconstruction_ = 0;
        }
    }

    void CEkltTrackerOrchestrator::initializeFromFirstImage()
    {
        if (initialized_ || images_.empty())
        {
            return;
        }

        current_image_it_ = images_.begin();
        most_current_t_us_ = current_image_it_->first;
        std::vector<SPhotometricPatch> initialized_patches =
            createPatches(current_image_it_->second, config_.max_corners);
        const int initialized_count = static_cast<int>(initialized_patches.size());

        // Install the exact cache reference count before publishing any live
        // patch. A failed cache leaves only retired stable slots.
        if (initialized_count > 0)
        {
            optimizer_.precomputeGradientImage(current_image_it_->second.image,
                                               current_image_it_->first, initialized_count,
                                               config_.log_eps);
        }

        patches_ = std::move(initialized_patches);
        patches_.reserve(static_cast<std::size_t>(config_.max_corners));
        for (SPhotometricPatch &patch : patches_)
        {
            emitTrack(patch);
        }
        while (static_cast<int>(patches_.size()) < config_.max_corners)
        {
            SPhotometricPatch retired;
            retired.id = -1;
            retired.lost = true;
            lost_indices_.push_back(static_cast<int>(patches_.size()));
            patches_.push_back(std::move(retired));
        }

        initialized_ = true;
        if (initialized_count > 0)
        {
            ++statistics_.initialization_count;
            statistics_.last_initialized_count = initialized_count;
        }
    }

    void CEkltTrackerOrchestrator::processEvent(const SEventSample &event)
    {
        most_current_t_us_ = std::max(most_current_t_us_, event.t_us);
        for (SPhotometricPatch &patch : patches_)
        {
            updatePatch(patch, event);
        }

        if (advanceCurrentImageBefore(most_current_t_us_))
        {
            if (config_.bootstrap_mode == ETrackerBootstrapMode::Klt)
            {
                bootstrapAllPossiblePatches();
            }
            if (activeTrackCount() < config_.min_corners)
            {
                addFeatures();
            }

            // Once every KLT bootstrap referencing an older image has run, the
            // complete stale prefix can no longer affect tracker state.
            images_.erase(images_.begin(), current_image_it_);
        }
    }

    bool CEkltTrackerOrchestrator::advanceCurrentImageBefore(int64_t t_us)
    {
        if (images_.empty() || current_image_it_ == images_.end())
        {
            return false;
        }

        bool advanced = false;
        TImageBuffer::iterator next_image_it = current_image_it_;
        while (next_image_it->first < t_us)
        {
            ++next_image_it;
            if (next_image_it == images_.end())
            {
                break;
            }
            if (next_image_it->first < t_us)
            {
                current_image_it_ = next_image_it;
                advanced = true;
            }
        }
        return advanced;
    }

    void CEkltTrackerOrchestrator::updatePatch(SPhotometricPatch &patch, const SEventSample &event)
    {
        if (patch.lost ||
            (config_.bootstrap_mode == ETrackerBootstrapMode::Klt && !patch.initialized) ||
            !patch.contains(event.x, event.y) || patch.t_curr_us > event.t_us)
        {
            return;
        }

        patch.insert(event);
        if (!patch.readyForUpdate())
        {
            return;
        }

        cv::Mat event_frame;
        if (!patch.getEventFrameAndReset(&event_frame))
        {
            return;
        }
        if (!patch.initialized && config_.bootstrap_mode == ETrackerBootstrapMode::Events)
        {
            CPhotometricOptimizer::bootstrapFlowFromEventFrame(&patch, event_frame);
            if (!patch.initialized)
            {
                return;
            }
        }
        if (!optimizer_.optimize(event_frame, &patch))
        {
            return;
        }

        statistics_.optimization_updates = SaturatingAdd(statistics_.optimization_updates, 1U);
        emitTrack(patch);
        setBatchSize(patch);
        if (shouldDiscard(patch))
        {
            const std::size_t index = static_cast<std::size_t>(&patch - patches_.data());
            retirePatch(patch, index);
        }
    }

    void CEkltTrackerOrchestrator::bootstrapAllPossiblePatches()
    {
        for (std::size_t index = 0; index < patches_.size(); ++index)
        {
            SPhotometricPatch &patch = patches_[index];
            if (patch.initialized || patch.lost || patch.t_init_us == current_image_it_->first)
            {
                continue;
            }

            const TImageBuffer::const_iterator initialization_it = images_.find(patch.t_init_us);
            if (initialization_it == images_.end())
            {
                retirePatch(patch, index);
                continue;
            }
            bootstrapFeatureKlt(patch, initialization_it->second.image,
                                current_image_it_->second.image);
            if (!patch.lost)
            {
                setBatchSize(patch);
            }
        }
    }

    void CEkltTrackerOrchestrator::bootstrapFeatureKlt(SPhotometricPatch &patch,
                                                       const cv::Mat &last_image,
                                                       const cv::Mat &current_image)
    {
        const cv::Mat last_klt_image = PrepareKltImage(last_image);
        const cv::Mat current_klt_image = PrepareKltImage(current_image);
        const std::size_t index = static_cast<std::size_t>(&patch - patches_.data());
        if (last_klt_image.empty() || current_klt_image.empty() ||
            last_klt_image.size() != current_klt_image.size())
        {
            retirePatch(patch, index);
            return;
        }

        const std::vector<cv::Point2f> points = {
            cv::Point2f(static_cast<float>(patch.init_center.x),
                        static_cast<float>(patch.init_center.y)),
        };
        std::vector<cv::Point2f> next_points;
        std::vector<float> errors;
        std::vector<unsigned char> status;
        const cv::Size window(config_.lk_window_size, config_.lk_window_size);
        cv::calcOpticalFlowPyrLK(last_klt_image, current_klt_image, points, next_points, status,
                                 errors, window, config_.num_pyramidal_layers);
        if (next_points.empty() || status.empty() || errors.empty() || status.front() == 0U ||
            !std::isfinite(next_points.front().x) || !std::isfinite(next_points.front().y) ||
            !std::isfinite(errors.front()) ||
            static_cast<double>(errors.front()) > config_.lk_max_error)
        {
            retirePatch(patch, index);
            return;
        }

        const cv::Point2f displacement = next_points.front() - points.front();
        patch.flow_angle = std::atan2(displacement.y, displacement.x);
        patch.warping.at<double>(0, 2) = -displacement.x;
        patch.warping.at<double>(1, 2) = -displacement.y;
        patch.warpPixel(patch.init_center, &patch.center);
        if (shouldDiscard(patch))
        {
            retirePatch(patch, index);
            return;
        }

        patch.initialized = true;
        patch.t_curr_us = current_image_it_->first;
        emitTrack(patch);
    }

    std::vector<SPhotometricPatch> CEkltTrackerOrchestrator::createPatches(const SImageFrame &frame,
                                                                           int count)
    {
        std::vector<SPhotometricPatch> patches;
        if (count <= 0)
        {
            return patches;
        }

        SFrameHarrisConfig harris_config;
        harris_config.max_corners = count;
        harris_config.quality_level = config_.quality_level;
        harris_config.min_distance = config_.min_distance;
        harris_config.block_size = config_.block_size;
        harris_config.k = config_.harris_k;
        harris_config.border = (config_.patch_size - 1) / 2;
        for (const SPhotometricPatch &patch : patches_)
        {
            if (!patch.lost)
            {
                harris_config.excluded_centers.push_back(patch.center);
            }
        }

        std::unique_ptr<CFeatureCandidateProvider> candidate_provider;
        if (config_.initialization_mode == ETrackerInitializationMode::EventOnlyFibar)
        {
            candidate_provider = std::make_unique<CFibarHarrisCandidateProvider>(harris_config);
        }
        else
        {
            candidate_provider = std::make_unique<CFrameHarrisCandidateProvider>(harris_config);
        }

        std::vector<SFeatureCandidate> candidates;
        if (!candidate_provider->detectCandidates(frame, count, &candidates))
        {
            return patches;
        }

        patches.reserve(candidates.size());
        for (const SFeatureCandidate &candidate : candidates)
        {
            SPhotometricPatch patch(next_track_id_, candidate.center, candidate.t_us,
                                    config_.patch_size, config_.batch_size,
                                    config_.update_every_n_events);
            if (!initializePatchFromFrame(frame, &patch))
            {
                continue;
            }
            ++next_track_id_;
            setBatchSize(patch);
            patches.push_back(std::move(patch));
        }
        return patches;
    }

    bool CEkltTrackerOrchestrator::initializePatchFromFrame(const SImageFrame &frame,
                                                            SPhotometricPatch *patch) const
    {
        if (patch == nullptr)
        {
            return false;
        }

        SFramePatchConfig patch_config;
        patch_config.log_eps = config_.log_eps;
        CFramePatchProvider frame_provider(frame, patch_config);
        CFeaturePatchProvider *provider = &frame_provider;
        std::unique_ptr<CFibarPatchProvider> fibar_provider;
        if (config_.initialization_mode == ETrackerInitializationMode::EventOnlyFibar)
        {
            fibar_provider = std::make_unique<CFibarPatchProvider>(
                [&frame_provider](const SFeatureCandidate &candidate, int radius,
                                  SLocalFeaturePatch *local_patch)
                { return frame_provider.requestPatch(candidate, radius, local_patch); });
            provider = fibar_provider.get();
        }

        SFeatureCandidate candidate;
        candidate.center = patch->init_center;
        candidate.t_us = patch->t_init_us;
        candidate.id = patch->id;
        SLocalFeaturePatch local_patch;
        if (!provider->requestPatch(candidate, patch->half_size, &local_patch))
        {
            return false;
        }

        CFeatureInitializer initializer;
        SInitializedFeature initialized;
        if (!initializer.initialize(candidate, local_patch, &initialized))
        {
            return false;
        }
        patch->gradient_x = initialized.patch.gradient_x.clone();
        patch->gradient_y = initialized.patch.gradient_y.clone();
        return true;
    }

    void CEkltTrackerOrchestrator::addFeatures()
    {
        if (lost_indices_.empty())
        {
            return;
        }

        std::vector<SPhotometricPatch> replacements =
            createPatches(current_image_it_->second, static_cast<int>(lost_indices_.size()));
        if (replacements.empty())
        {
            statistics_.last_initialized_count = 0;
            return;
        }

        optimizer_.precomputeGradientImage(current_image_it_->second.image,
                                           current_image_it_->first,
                                           static_cast<int>(replacements.size()), config_.log_eps);

        const std::size_t replacement_count = std::min(replacements.size(), lost_indices_.size());
        for (std::size_t index = 0; index < replacement_count; ++index)
        {
            const int slot = lost_indices_[index];
            patches_[static_cast<std::size_t>(slot)] = std::move(replacements[index]);
            emitTrack(patches_[static_cast<std::size_t>(slot)]);
        }
        lost_indices_.erase(lost_indices_.begin(),
                            lost_indices_.begin() + static_cast<std::ptrdiff_t>(replacement_count));
        ++statistics_.initialization_count;
        statistics_.last_initialized_count = static_cast<int>(replacement_count);
    }

    void CEkltTrackerOrchestrator::setBatchSize(SPhotometricPatch &patch) const
    {
        patch.batch_size =
            CPhotometricOptimizer::computeAdaptiveBatchSize(patch.gradient_x, patch.gradient_y,
                                                            patch.flow_angle,
                                                            config_.displacement_px,
                                                            config_.batch_size);
    }

    bool CEkltTrackerOrchestrator::shouldDiscard(const SPhotometricPatch &patch) const
    {
        const bool out_of_fov = patch.center.x < 0.0 || patch.center.y < 0.0 ||
                                patch.center.x >= static_cast<double>(config_.width) ||
                                patch.center.y >= static_cast<double>(config_.height);
        const bool low_quality = patch.tracking_quality < config_.tracking_quality;
        return out_of_fov || low_quality;
    }

    void CEkltTrackerOrchestrator::retirePatch(SPhotometricPatch &patch, std::size_t index)
    {
        if (patch.lost)
        {
            return;
        }

        // Retire the cache reference at the exact live-to-lost transition so
        // interface layers never own native gradient lifetime.
        optimizer_.releaseGradientImageReference(patch.t_init_us);
        patch.lost = true;
        patch.event_buffer.clear();
        patch.gradient_x.release();
        patch.gradient_y.release();
        ++statistics_.lost_count;

        const int slot = static_cast<int>(index);
        if (std::find(lost_indices_.begin(), lost_indices_.end(), slot) == lost_indices_.end())
        {
            lost_indices_.push_back(slot);
        }
    }

    void CEkltTrackerOrchestrator::emitTrack(const SPhotometricPatch &patch)
    {
        track_samples_.push_back(STrackSample{
            patch.id,
            patch.t_curr_us,
            patch.center,
        });
    }

    bool CEkltTrackerOrchestrator::initialized() const
    {
        return initialized_;
    }

    int CEkltTrackerOrchestrator::activeTrackCount() const
    {
        return static_cast<int>(std::count_if(patches_.begin(), patches_.end(),
                                              [](const SPhotometricPatch &patch)
                                              { return !patch.lost; }));
    }

    STrackerSnapshot CEkltTrackerOrchestrator::snapshot() const
    {
        STrackerSnapshot output;
        if (!initialized_ || current_image_it_ == images_.end())
        {
            return output;
        }

        output.image = CloneFrame(current_image_it_->second);
        output.tracks.reserve(patches_.size());
        for (const SPhotometricPatch &patch : patches_)
        {
            output.tracks.push_back(MakeTrackState(patch));
        }
        output.t_us = most_current_t_us_;
        output.statistics = currentStatistics();
        return output;
    }

    std::vector<STrackSample> CEkltTrackerOrchestrator::takeTrackSamples()
    {
        std::vector<STrackSample> samples;
        samples.swap(track_samples_);
        return samples;
    }

    STrackerStatistics CEkltTrackerOrchestrator::currentStatistics() const
    {
        STrackerStatistics output = statistics_;
        output.active_tracks = activeTrackCount();
        return output;
    }

    STrackerStatistics CEkltTrackerOrchestrator::statistics() const
    {
        return currentStatistics();
    }

    std::size_t CEkltTrackerOrchestrator::gradientCacheCount() const
    {
        return optimizer_.gradientCacheCount();
    }

    const SEkltTrackerConfig &CEkltTrackerOrchestrator::config() const
    {
        return config_;
    }

} // namespace eklt_core
