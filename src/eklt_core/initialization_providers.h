/// @file initialization_providers.h
/// @brief Defines ROS-free feature initialization provider contracts.
/// @details Frame-backed and reconstructed-image initialization remain
///          interchangeable, while candidate and local-patch providers can be
///          composed independently.

#ifndef EKLT_CORE_INITIALIZATION_PROVIDERS_H_
#define EKLT_CORE_INITIALIZATION_PROVIDERS_H_

#include <cstdint>
#include <functional>
#include <vector>

#include <opencv2/core/core.hpp>

namespace eklt_core
{

    /// @brief Identifies why an initialization image is requested.
    enum class EImageRequestReason
    {
        /// @brief First tracker initialization.
        InitialBootstrap,
        /// @brief Replacement of lost or depleted features.
        FeatureReinitialization,
        /// @brief Image requested only for diagnostic output.
        DebugVisualization
    };

    /// @brief Image and timestamp supplied to candidate and patch providers.
    struct SImageFrame
    {
        /// @brief Single-channel image storage.
        cv::Mat image;
        /// @brief Absolute image timestamp in microseconds.
        int64_t t_us{0};
        /// @brief Declared sensor width in pixels.
        int width{0};
        /// @brief Declared sensor height in pixels.
        int height{0};
        /// @brief Non-owning coordinate-frame identifier.
        const char *frame_id{"event_camera"};

        /// @brief Check whether storage and declared geometry describe one image.
        /// @return True for a non-empty, single-channel 2D image whose declared
        ///         geometry exactly matches its OpenCV storage.
        bool valid() const;
    };

    /// @brief Sparse feature location proposed for EKLT initialization.
    struct SFeatureCandidate
    {
        /// @brief Candidate center in image coordinates.
        cv::Point2d center;
        /// @brief Provider-defined candidate response.
        double response{0.0};
        /// @brief Provider-defined feature scale.
        double scale{1.0};
        /// @brief Absolute candidate timestamp in microseconds.
        int64_t t_us{0};
        /// @brief Provider-assigned identifier, or `-1` when unspecified.
        int id{-1};
    };

    /// @brief Local intensity, gradients, and validity used to initialize a feature.
    struct SLocalFeaturePatch
    {
        /// @brief Normalized `CV_64F` intensity plane.
        cv::Mat intensity;
        /// @brief Horizontal `CV_64F` log-intensity gradient.
        cv::Mat gradient_x;
        /// @brief Vertical `CV_64F` log-intensity gradient.
        cv::Mat gradient_y;
        /// @brief `CV_8U` mask whose nonzero pixels are valid samples.
        cv::Mat valid_mask;
        /// @brief Patch center in source-image coordinates.
        cv::Point2d center;
        /// @brief Absolute source timestamp in microseconds.
        int64_t t_us{0};
        /// @brief Fraction of patch pixels backed by the source image.
        double valid_fraction{0.0};
        /// @brief Mean squared gradient magnitude over valid pixels.
        double gradient_energy{0.0};

        /// @brief Check whether every patch plane satisfies the shared geometry.
        /// @return True when all patch planes are non-empty and shape-compatible.
        bool valid() const;
    };

    /// @brief Accepted candidate paired with its initialized local patch.
    struct SInitializedFeature
    {
        /// @brief Candidate metadata accepted by the initializer.
        SFeatureCandidate candidate;
        /// @brief Validated local patch associated with `candidate`.
        SLocalFeaturePatch patch;
    };

    /// @brief Harris candidate detector configuration for frame-like images.
    struct SFrameHarrisConfig
    {
        /// @brief Maximum corners considered by the detector.
        int max_corners{100};
        /// @brief Minimum accepted corner-quality ratio.
        double quality_level{0.01};
        /// @brief Minimum separation between returned candidates in pixels.
        double min_distance{10.0};
        /// @brief Harris neighborhood block size.
        int block_size{3};
        /// @brief Harris free parameter.
        double k{0.04};
        /// @brief Excluded image border width in pixels.
        int border{0};
        /// @brief Centers around which new candidates are suppressed.
        std::vector<cv::Point2d> excluded_centers;
    };

    /// @brief Log-gradient configuration for frame-backed local patches.
    struct SFramePatchConfig
    {
        /// @brief Positive offset applied before the logarithm.
        double log_eps{1e-2};
    };

    /// @brief Abstract source of latest-causal initialization images.
    class CInitializationImageProvider
    {
      public:
        /// @brief Destroy the polymorphic image provider.
        virtual ~CInitializationImageProvider();

        /// @brief Request an image at or before a timestamp.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @param reason Purpose of the request.
        /// @param image Output frame when available.
        /// @return True when a causal image was written.
        virtual bool requestImage(int64_t t_us,
                                  EImageRequestReason reason,
                                  SImageFrame *image) = 0;
    };

    /// @brief Abstract detector of sparse feature candidates.
    class CFeatureCandidateProvider
    {
      public:
        /// @brief Destroy the polymorphic candidate provider.
        virtual ~CFeatureCandidateProvider();

        /// @brief Detect up to a requested number of candidates.
        /// @param image Source image and timestamp.
        /// @param max_candidates Maximum number of returned candidates.
        /// @param candidates Output candidates in provider-defined priority order.
        /// @return True when the request was valid, including an empty result.
        virtual bool detectCandidates(const SImageFrame &image,
                                      int max_candidates,
                                      std::vector<SFeatureCandidate> *candidates) = 0;
    };

    /// @brief Abstract source of local intensity and gradient patches.
    class CFeaturePatchProvider
    {
      public:
        /// @brief Destroy the polymorphic patch provider.
        virtual ~CFeaturePatchProvider();

        /// @brief Request a local patch for one feature candidate.
        /// @param candidate Candidate center and timestamp.
        /// @param radius Nonnegative patch radius.
        /// @param patch Output patch.
        /// @return True when a valid request was processed.
        virtual bool requestPatch(const SFeatureCandidate &candidate,
                                  int radius,
                                  SLocalFeaturePatch *patch) = 0;
    };

    /// @brief Serves one immutable frame as a causal image provider.
    class CFrameCameraImageProvider : public CInitializationImageProvider
    {
      public:
        /// @brief Construct a provider for one immutable frame.
        /// @param frame Frame retained by value for future requests.
        explicit CFrameCameraImageProvider(const SImageFrame &frame);

        /// @copydoc CInitializationImageProvider::requestImage
        bool requestImage(int64_t t_us,
                          EImageRequestReason reason,
                          SImageFrame *image) override;

      private:
        SImageFrame frame_;
    };

    /// @brief Adapts a callable to the initialization-image provider contract.
    class CCallbackImageProvider : public CInitializationImageProvider
    {
      public:
        /// @brief Callable signature matching `requestImage`.
        using TCallback = std::function<bool(int64_t, EImageRequestReason, SImageFrame *)>;

        /// @brief Construct an image provider around one callback.
        /// @param callback Callable retained by value.
        explicit CCallbackImageProvider(TCallback callback);

        /// @copydoc CInitializationImageProvider::requestImage
        bool requestImage(int64_t t_us,
                          EImageRequestReason reason,
                          SImageFrame *image) override;

      private:
        TCallback callback_;
    };

    /// @brief Detects Harris corners while excluding borders and active tracks.
    class CFrameHarrisCandidateProvider : public CFeatureCandidateProvider
    {
      public:
        /// @brief Construct a Harris candidate provider.
        /// @param config Harris detector and exclusion configuration.
        /// @throws std::invalid_argument If the configuration contains an
        ///         invalid range or non-finite value.
        explicit CFrameHarrisCandidateProvider(const SFrameHarrisConfig &config);

        /// @copydoc CFeatureCandidateProvider::detectCandidates
        bool detectCandidates(const SImageFrame &image,
                              int max_candidates,
                              std::vector<SFeatureCandidate> *candidates) override;

      private:
        SFrameHarrisConfig config_;
    };

    /// @brief Extracts normalized intensity and log-gradient patches from a frame.
    class CFramePatchProvider : public CFeaturePatchProvider
    {
      public:
        /// @brief Construct a patch provider and precompute source gradients.
        /// @param frame Source frame retained by value.
        /// @param config Log-gradient configuration.
        /// @throws std::invalid_argument If `config.log_eps` is not finite and
        ///         strictly positive.
        explicit CFramePatchProvider(const SImageFrame &frame,
                                     const SFramePatchConfig &config = SFramePatchConfig());

        /// @copydoc CFeaturePatchProvider::requestPatch
        bool requestPatch(const SFeatureCandidate &candidate,
                          int radius,
                          SLocalFeaturePatch *patch) override;

      private:
        static void computeGradients(const cv::Mat &normalized_image,
                                     double log_eps,
                                     cv::Mat &gradient_x,
                                     cv::Mat &gradient_y);

        SImageFrame frame_;
        SFramePatchConfig config_;
        cv::Mat normalized_intensity_;
        cv::Mat gradient_x_;
        cv::Mat gradient_y_;
    };

    /// @brief Adapts a callable to the local-patch provider contract.
    class CCallbackPatchProvider : public CFeaturePatchProvider
    {
      public:
        /// @brief Callable signature matching `requestPatch`.
        using TCallback = std::function<bool(const SFeatureCandidate &, int, SLocalFeaturePatch *)>;

        /// @brief Construct a patch provider around one callback.
        /// @param callback Callable retained by value.
        explicit CCallbackPatchProvider(TCallback callback);

        /// @copydoc CFeaturePatchProvider::requestPatch
        bool requestPatch(const SFeatureCandidate &candidate,
                          int radius,
                          SLocalFeaturePatch *patch) override;

      private:
        TCallback callback_;
    };

    /// @brief Names a callback image source as a FIBAR-backed provider.
    class CFibarImageProvider : public CCallbackImageProvider
    {
      public:
        /// @brief Construct a named FIBAR image-provider adapter.
        /// @param callback FIBAR image request callback.
        explicit CFibarImageProvider(TCallback callback);
    };

    /// @brief Applies the frame Harris detector to FIBAR-reconstructed images.
    class CFibarHarrisCandidateProvider : public CFrameHarrisCandidateProvider
    {
      public:
        /// @brief Construct a Harris detector for reconstructed FIBAR images.
        /// @param config Harris detector and exclusion configuration.
        explicit CFibarHarrisCandidateProvider(const SFrameHarrisConfig &config);
    };

    /// @brief Names a callback local-patch source as a FIBAR-backed provider.
    class CFibarPatchProvider : public CCallbackPatchProvider
    {
      public:
        /// @brief Construct a named FIBAR patch-provider adapter.
        /// @param callback FIBAR local-patch request callback.
        explicit CFibarPatchProvider(TCallback callback);
    };

    /// @brief Validates and joins a candidate with its local initialization patch.
    class CFeatureInitializer
    {
      public:
        /// @brief Create an initialized feature from compatible provider outputs.
        /// @param candidate Sparse candidate metadata.
        /// @param patch Local intensity and gradient data.
        /// @param feature Output initialized feature.
        /// @return True when the patch is valid and contains at least one valid pixel.
        bool initialize(const SFeatureCandidate &candidate,
                        const SLocalFeaturePatch &patch,
                        SInitializedFeature *feature) const;
    };

} // namespace eklt_core

#endif // EKLT_CORE_INITIALIZATION_PROVIDERS_H_
