/// @file fibar_reconstructor.h
/// @brief Declares the stable ROS-free facade over the upstream FIBAR library.
/// @details The facade accepts typed event-array views, preserves absolute
///          microsecond timestamps, and owns reconstructed image storage.

#ifndef EVENT_RECON_FIBAR_CORE_FIBAR_RECONSTRUCTOR_H_
#define EVENT_RECON_FIBAR_CORE_FIBAR_RECONSTRUCTOR_H_

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

namespace fibar_lib
{
    template <bool filter_spatially, std::uint8_t tile_size>
    class ImageReconstructor;
}

namespace event_recon_fibar_core
{

    /// @brief One signed-polarity event expressed in sensor coordinates.
    struct SEvent
    {
        /// @brief Sensor x coordinate in pixels.
        uint16_t x{0};
        /// @brief Sensor y coordinate in pixels.
        uint16_t y{0};
        /// @brief Signed event polarity.
        int8_t p{1};
        /// @brief Absolute event timestamp in microseconds.
        int64_t t_us{0};
    };

    /// @brief Non-owning, structure-of-arrays view over one ordered event batch.
    /// @details All arrays must contain at least `size` elements. Non-empty
    ///          batches must be monotonically nondecreasing both internally and
    ///          relative to all batches previously accepted by the reconstructor.
    struct SEventBatchView
    {
        /// @brief Non-owning x-coordinate array.
        const uint16_t *x{nullptr};
        /// @brief Non-owning y-coordinate array.
        const uint16_t *y{nullptr};
        /// @brief Non-owning signed-polarity array.
        const int8_t *p{nullptr};
        /// @brief Non-owning absolute-timestamp array in microseconds.
        const int64_t *t_us{nullptr};
        /// @brief Number of events available in every array.
        std::size_t size{0};
        /// @brief Optional batch sensor width, or zero when unspecified.
        int width{0};
        /// @brief Optional batch sensor height, or zero when unspecified.
        int height{0};
    };

    /// @brief Configuration required to initialize a FIBAR reconstruction state.
    struct SFibarConfig
    {
        /// @brief Sensor width in pixels.
        int width{0};
        /// @brief Sensor height in pixels.
        int height{0};
        /// @brief Upstream filter cutoff interval in microseconds.
        uint32_t cutoff_time_us{10000};
        /// @brief Spatial-filter fill ratio in `(0, 1]`.
        double fill_ratio{0.5};
        /// @brief Whether to use the spatial rather than temporal reconstructor.
        bool use_spatial_filter{true};
    };

    /// @brief Non-owning view of the reconstructor's latest causal float image.
    /// @details The data remains owned by the reconstructor and may be invalidated
    ///          by the next mutating operation.
    struct SReconstructedImageView
    {
        /// @brief Non-owning row-major float image storage.
        const float *data{nullptr};
        /// @brief Number of elements available through `data`.
        std::size_t size{0};
        /// @brief Image width in pixels.
        int width{0};
        /// @brief Image height in pixels.
        int height{0};
        /// @brief Absolute timestamp of the reconstructed state in microseconds.
        int64_t t_us{0};
    };

    /// @brief Owning local intensity and gradient patch returned by FIBAR.
    struct SLocalFeaturePatch
    {
        /// @brief Row-major reconstructed intensity samples.
        std::vector<float> intensity;
        /// @brief Row-major horizontal intensity gradients.
        std::vector<float> gradient_x;
        /// @brief Row-major vertical intensity gradients.
        std::vector<float> gradient_y;
        /// @brief Row-major validity mask with nonzero valid samples.
        std::vector<uint8_t> valid_mask;
        /// @brief Patch width in pixels.
        int width{0};
        /// @brief Patch height in pixels.
        int height{0};
        /// @brief Patch center x coordinate in the sensor image.
        int center_x{0};
        /// @brief Patch center y coordinate in the sensor image.
        int center_y{0};
        /// @brief Absolute reconstructed-image timestamp in microseconds.
        int64_t t_us{0};
        /// @brief Fraction of patch pixels backed by the sensor image.
        float valid_fraction{0.0F};
        /// @brief Mean squared gradient magnitude over valid pixels.
        float gradient_energy{0.0F};
    };

    /// @brief Normalize a float reconstruction for display without changing core data.
    /// @param image Contiguous float input, or null only when `image_size` is zero.
    /// @param image_size Number of pixels in `image`.
    /// @return Min-max normalized 8-bit display pixels.
    /// @throws std::invalid_argument If a non-empty input has a null pointer.
    /// @throws std::runtime_error If an input value is not finite.
    /// @details Range arithmetic uses double precision so every finite float input
    ///          remains representable during normalization.
    std::vector<uint8_t> NormalizeImageForDisplay(const float *image, std::size_t image_size);

    /// @brief Owns one validated, ROS-free FIBAR reconstruction stream.
    /// @details Selects and owns the upstream spatial or temporal filter
    ///          directly while keeping its implementation header private.
    class CFibarReconstructor
    {
      public:
        /// @brief Construct an empty reconstruction with fixed sensor geometry.
        /// @param config Sensor and FIBAR filter configuration.
        /// @throws std::invalid_argument If the configuration is invalid.
        explicit CFibarReconstructor(const SFibarConfig &config);

        /// @brief Destroy the owned reconstruction state.
        ~CFibarReconstructor();

        /// @brief Transfer ownership from another reconstructor.
        /// @param other Source reconstructor left empty after the transfer.
        CFibarReconstructor(CFibarReconstructor &&other) noexcept;

        /// @brief Transfer ownership from another reconstructor.
        /// @param other Source reconstructor left empty after the transfer.
        /// @return This reconstructor after replacing its owned state.
        CFibarReconstructor &operator=(CFibarReconstructor &&other) noexcept;

        /// @brief Disable copying of reconstruction state.
        CFibarReconstructor(const CFibarReconstructor &) = delete;
        /// @brief Disable copy assignment of reconstruction state.
        CFibarReconstructor &operator=(const CFibarReconstructor &) = delete;

        /// @brief Clear all events and restore the configured initial state.
        void reset();

        /// @brief Accept the next monotonically ordered event batch.
        /// @param events Non-owning event arrays consumed during this call.
        /// @throws std::invalid_argument If arrays, dimensions, or timestamps violate the contract.
        /// @throws std::out_of_range If an event lies outside the sensor.
        /// @throws std::runtime_error If relative timestamps exceed the upstream clock range.
        void acceptEvents(const SEventBatchView &events);

        /// @brief Check whether the latest reconstructed state is causal for a request.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return True when an accepted reconstruction exists at or before `t_us`.
        bool hasImageFor(int64_t t_us) const;

        /// @brief Return the latest causal float image.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Non-owning image view backed by this reconstructor.
        /// @throws std::runtime_error If no causal image exists.
        SReconstructedImageView requestImage(int64_t t_us) const;

        /// @brief Copy the current image into caller-owned storage.
        /// @param output Destination buffer.
        /// @param output_size Number of float elements available in `output`.
        /// @throws std::invalid_argument If the pointer or size is invalid.
        void copyImageTo(float *output, std::size_t output_size) const;

        /// @brief Return a display-normalized image for a causal timestamp.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Owned 8-bit image in row-major order.
        std::vector<uint8_t> makeDisplayImage(int64_t t_us) const;

        /// @brief Extract an owned local patch from the latest causal image.
        /// @param center_x Patch center x coordinate.
        /// @param center_y Patch center y coordinate.
        /// @param radius Nonnegative patch radius.
        /// @param t_us Requested absolute timestamp in microseconds.
        /// @return Intensity, gradient, validity, and quality data.
        /// @throws std::invalid_argument If `radius` cannot form a representable
        ///         odd patch size.
        SLocalFeaturePatch requestPatch(int center_x, int center_y, int radius, int64_t t_us) const;

        /// @brief Return the configured sensor width.
        /// @return Configured sensor width in pixels.
        int width() const;
        /// @brief Return the configured sensor height.
        /// @return Configured sensor height in pixels.
        int height() const;
        /// @brief Return the timestamp of the latest accepted event.
        /// @return Absolute timestamp of the latest accepted event, or `-1`.
        int64_t latestTimestampUs() const;

      private:
        using TSpatialReconstructor = fibar_lib::ImageReconstructor<true, 2>;
        using TTemporalReconstructor = fibar_lib::ImageReconstructor<false, 2>;

        void initialize();
        void validateBatch(const SEventBatchView &events) const;
        void refreshImage() const;

        template <typename TStateVector>
        void copyState(const TStateVector &state) const;

        SFibarConfig config_;
        std::unique_ptr<TSpatialReconstructor> spatial_;
        std::unique_ptr<TTemporalReconstructor> temporal_;
        mutable std::vector<float> image_;
        int64_t time_origin_us_{-1};
        int64_t latest_t_us_{-1};
    };

} // namespace event_recon_fibar_core

#endif // EVENT_RECON_FIBAR_CORE_FIBAR_RECONSTRUCTOR_H_
