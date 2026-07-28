/// @file tracker_orchestrator.h
/// @brief Declares the complete ROS-free EKLT tracking state machine.
/// @details The orchestrator owns image and event scheduling, FIBAR
///          reconstruction, feature initialization and lifecycle, optical-flow
///          bootstrap, photometric optimization, and wrapper-friendly outputs.
///          ROS1, ROS2, Python, and MATLAB integrations remain interface
///          adapters around this C++17 API.

#ifndef EKLT_CORE_TRACKER_ORCHESTRATOR_H_
#define EKLT_CORE_TRACKER_ORCHESTRATOR_H_

#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <memory>
#include <vector>

#include <opencv2/core.hpp>

#include "eklt_core/initialization_providers.h"
#include "eklt_core/photometric_patch_tracker.h"

namespace event_recon_fibar_core
{
    class CFibarReconstructor;
}

namespace eklt_core
{

    /// @brief Selects the source of tracker initialization images.
    enum class ETrackerInitializationMode
    {
        /// @brief Consume externally supplied camera frames.
        FrameBacked,
        /// @brief Reconstruct causal initialization images from events.
        EventOnlyFibar
    };

    /// @brief Selects the optical-flow direction bootstrap.
    enum class ETrackerBootstrapMode
    {
        /// @brief Bootstrap from two causal images with pyramidal KLT.
        Klt,
        /// @brief Bootstrap from the first informative local event frame.
        Events
    };

    /// @brief Complete ROS-free runtime configuration for EKLT orchestration.
    struct SEkltTrackerConfig
    {
        /// @brief Fixed sensor width in pixels.
        int width{0};
        /// @brief Fixed sensor height in pixels.
        int height{0};
        /// @brief Initialization-image source.
        ETrackerInitializationMode initialization_mode{ETrackerInitializationMode::FrameBacked};
        /// @brief Optical-flow bootstrap method.
        ETrackerBootstrapMode bootstrap_mode{ETrackerBootstrapMode::Klt};

        /// @brief Maximum number of stable feature slots.
        int max_corners{100};
        /// @brief Live-feature threshold below which reinitialization is attempted.
        int min_corners{60};
        /// @brief Minimum candidate separation in pixels.
        double min_distance{30.0};
        /// @brief Minimum Harris response relative to the strongest corner.
        double quality_level{0.3};
        /// @brief Harris detector neighborhood size.
        int block_size{30};
        /// @brief Harris detector free parameter.
        double harris_k{0.04};

        /// @brief Odd side length of each photometric patch.
        int patch_size{25};
        /// @brief Maximum retained events in each patch.
        int batch_size{200};
        /// @brief New events required between optimization attempts.
        int update_every_n_events{20};
        /// @brief Maximum Ceres iterations per photometric update.
        int max_num_iterations{10};
        /// @brief KLT search-window side length.
        int lk_window_size{15};
        /// @brief KLT maximum pyramid level.
        int num_pyramidal_layers{2};
        /// @brief Maximum accepted KLT residual; defaults to no practical limit.
        double lk_max_error{std::numeric_limits<double>::max()};

        /// @brief Target displacement used for adaptive batch sizing.
        double displacement_px{0.6};
        /// @brief Minimum accepted photometric tracking quality.
        double tracking_quality{0.4};
        /// @brief Positive intensity offset applied before log gradients.
        double log_eps{1e-2};
        /// @brief Earliest accepted initialization-image timestamp.
        int64_t first_image_t_us{-1};

        /// @brief Accepted events between event-only image reconstructions.
        int reconstruction_interval_events{5000};
        /// @brief FIBAR temporal cutoff in microseconds.
        uint32_t fibar_cutoff_time_us{10000};
        /// @brief FIBAR spatial-filter fill ratio.
        double fibar_fill_ratio{0.5};
        /// @brief Select the FIBAR spatial rather than temporal filter.
        bool fibar_use_spatial_filter{true};
    };

    /// @brief One emitted track row independent of transport and file formats.
    struct STrackSample
    {
        /// @brief Stable feature identifier.
        int id{0};
        /// @brief Absolute sample timestamp in microseconds.
        int64_t t_us{0};
        /// @brief Current feature center in image coordinates.
        cv::Point2d center;
    };

    /// @brief Monotonic counters describing one orchestrator lifetime.
    struct STrackerStatistics
    {
        /// @brief Event samples accepted at the native boundary.
        uint64_t accepted_events{0};
        /// @brief Event samples consumed by the tracking state machine.
        uint64_t processed_events{0};
        /// @brief Successful Ceres patch updates.
        uint64_t optimization_updates{0};
        /// @brief Initialization or reinitialization operations that added tracks.
        uint64_t initialization_count{0};
        /// @brief Tracks added by the most recent initialization operation.
        int last_initialized_count{0};
        /// @brief Tracks retired during this lifetime.
        uint64_t lost_count{0};
        /// @brief Currently live feature slots.
        int active_tracks{0};
    };

    /// @brief Wall-clock decomposition for the most recently accepted event batch.
    /// @details FIBAR time covers event ingestion and any requested causal-image
    ///          reconstruction. EKLT time covers all remaining native validation,
    ///          ordering, initialization, scheduling, and optimization work.
    struct STrackerTimingSample
    {
        /// @brief Timestamp of the newest event in the accepted batch.
        int64_t t_us{-1};
        /// @brief FIBAR reconstruction wall time in milliseconds.
        double fibar_ms{0.0};
        /// @brief Native EKLT wall time excluding FIBAR in milliseconds.
        double eklt_ms{0.0};
        /// @brief Complete native event-batch wall time in milliseconds.
        double native_total_ms{0.0};

        /// @brief Check finite, nonnegative, additive timing invariants.
        /// @return True when the sample describes one accepted non-empty batch.
        bool valid() const;
    };

    /// @brief Lightweight owning state for one track at a snapshot boundary.
    /// @details Excludes event buffers, gradients, and optimizer caches so
    ///          visualization and generated wrappers cannot retain algorithm
    ///          working storage.
    struct STrackState
    {
        /// @brief Stable feature identifier.
        int id{0};
        /// @brief Feature center at initialization.
        cv::Point2d init_center;
        /// @brief Current feature center.
        cv::Point2d center;
        /// @brief Absolute initialization timestamp in microseconds.
        int64_t t_init_us{0};
        /// @brief Absolute timestamp of the latest track update.
        int64_t t_curr_us{0};
        /// @brief Half-width of the square feature patch.
        int half_size{0};
        /// @brief Current optical-flow direction in radians.
        double flow_angle{0.0};
        /// @brief Solver-derived tracking quality.
        double tracking_quality{1.0};
        /// @brief Whether optical-flow bootstrap has completed.
        bool initialized{false};
        /// @brief Whether the stable feature slot has retired.
        bool lost{false};
        /// @brief Current homogeneous rigid patch warp.
        cv::Matx33d warping{cv::Matx33d::eye()};

        /// @brief Apply the inverse current warp to one reference pixel.
        /// @param unwarped Reference-image coordinate.
        /// @param warped Output current-image coordinate; ignored when null.
        void warpPixel(const cv::Point2d &unwarped, cv::Point2d *warped) const;
    };

    /// @brief Owning state snapshot for visualization and generated wrappers.
    struct STrackerSnapshot
    {
        /// @brief Current causal initialization image.
        SImageFrame image;
        /// @brief Lightweight fixed feature slots.
        std::vector<STrackState> tracks;
        /// @brief Latest event or image timestamp represented by the state.
        int64_t t_us{-1};
        /// @brief Statistics captured with the feature state.
        STrackerStatistics statistics;

        /// @brief Check whether the snapshot contains a valid image.
        /// @return True when the orchestrator has initialized.
        bool valid() const;
    };

    /// @brief Coordinates the complete EKLT algorithm without ROS dependencies.
    /// @details Public calls are synchronous and deterministic. Callers that
    ///          submit data from multiple threads must serialize access.
    class CEkltTrackerOrchestrator
    {
      public:
        /// @brief Construct an empty tracker for fixed sensor geometry.
        /// @param config Complete tracking and reconstruction configuration.
        /// @throws std::invalid_argument If any configuration invariant fails.
        explicit CEkltTrackerOrchestrator(const SEkltTrackerConfig &config);

        /// @brief Destroy native optimization and optional FIBAR state.
        ~CEkltTrackerOrchestrator();

        /// @brief Disable copying of optimizer, reconstruction, and iterators.
        CEkltTrackerOrchestrator(const CEkltTrackerOrchestrator &) = delete;
        /// @brief Disable copy assignment of stateful orchestration.
        CEkltTrackerOrchestrator &operator=(const CEkltTrackerOrchestrator &) = delete;
        /// @brief Disable moving because image-buffer iterators are internal.
        CEkltTrackerOrchestrator(CEkltTrackerOrchestrator &&) = delete;
        /// @brief Disable move assignment because image-buffer iterators are internal.
        CEkltTrackerOrchestrator &operator=(CEkltTrackerOrchestrator &&) = delete;

        /// @brief Clear all tracking state while retaining configuration.
        void reset();

        /// @brief Submit one immutable frame-backed initialization image.
        /// @param frame Valid scalar image matching configured sensor geometry.
        /// @return True when inserted; false for a duplicate, a frame no newer
        ///         than processed event state, or event-only mode.
        /// @throws std::invalid_argument If frame geometry, storage, or
        ///         timestamp violates the configured contract.
        bool acceptFrame(const SImageFrame &frame);

        /// @brief Submit one event batch and process every currently schedulable event.
        /// @param events Owning event batch; out-of-order samples are stably
        ///        reordered by timestamp.
        /// @return True when the complete batch was accepted.
        /// @throws std::invalid_argument If coordinates, polarity, or timestamps
        ///         violate the configured contract.
        /// @throws std::runtime_error If FIBAR cannot accept an event-only batch.
        bool acceptEvents(std::vector<SEventSample> events);

        /// @brief Report whether the first initialization image was consumed.
        /// @return True after tracker initialization.
        bool initialized() const;

        /// @brief Count currently live feature slots.
        /// @return Number of non-retired patches.
        int activeTrackCount() const;

        /// @brief Return an owning image and lightweight track-state copy.
        /// @return Owning snapshot, invalid before initialization.
        STrackerSnapshot snapshot() const;

        /// @brief Remove and return track rows emitted since the previous call.
        /// @return Track samples in deterministic emission order.
        std::vector<STrackSample> takeTrackSamples();

        /// @brief Return current monotonic counters.
        /// @return Statistics with an up-to-date active-track count.
        STrackerStatistics statistics() const;

        /// @brief Return timing for the most recently accepted non-empty event batch.
        /// @return Valid timing after a successful batch; invalid after reset or
        ///         a rejected or exceptional batch.
        STrackerTimingSample lastProcessingTiming() const;

        /// @brief Return the number of live timestamped gradient caches.
        /// @return Cache count owned by the native optimizer.
        std::size_t gradientCacheCount() const;

        /// @brief Return the validated immutable configuration.
        /// @return Configuration used for this lifetime.
        const SEkltTrackerConfig &config() const;

      private:
        using TImageBuffer = std::map<int64_t, SImageFrame>;

        void validateConfig() const;
        void validateEvents(const std::vector<SEventSample> &events) const;
        void initializeFromFirstImage();
        void processEvent(const SEventSample &event);
        bool advanceCurrentImageBefore(int64_t t_us);
        void bootstrapAllPossiblePatches();
        void bootstrapFeatureKlt(SPhotometricPatch &patch, const cv::Mat &last_image,
                                 const cv::Mat &current_image);
        void updatePatch(SPhotometricPatch &patch, const SEventSample &event);
        void addFeatures();
        std::vector<SPhotometricPatch> createPatches(const SImageFrame &frame, int count);
        bool initializePatchFromFrame(const SImageFrame &frame, SPhotometricPatch *patch) const;
        void setBatchSize(SPhotometricPatch &patch) const;
        bool shouldDiscard(const SPhotometricPatch &patch) const;
        void retirePatch(SPhotometricPatch &patch, std::size_t index);
        void emitTrack(const SPhotometricPatch &patch);
        void reconstructEventOnlyImage(const std::vector<SEventSample> &events);
        STrackerStatistics currentStatistics() const;

        SEkltTrackerConfig config_;
        TImageBuffer images_;
        TImageBuffer::iterator current_image_it_;
        std::vector<SPhotometricPatch> patches_;
        std::vector<int> lost_indices_;
        std::vector<STrackSample> track_samples_;
        CPhotometricOptimizer optimizer_;
        std::unique_ptr<event_recon_fibar_core::CFibarReconstructor> fibar_reconstructor_;
        STrackerStatistics statistics_;
        STrackerTimingSample last_processing_timing_;
        int next_track_id_{0};
        int64_t most_current_t_us_{-1};
        std::size_t events_since_reconstruction_{0};
        int64_t last_accepted_event_t_us_{-1};
        bool initialized_{false};
    };

} // namespace eklt_core

#endif // EKLT_CORE_TRACKER_ORCHESTRATOR_H_
