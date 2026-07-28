/// @file reconstructed_frame_writer.h
/// @brief Declares bounded PNG persistence for reconstructed EKLT frames.
/// @details The stateful writer belongs to the ROS2 output boundary and stores
///          no image history beyond counters and the last observed timestamp.

#ifndef EKLT_REBUILD_RECONSTRUCTED_FRAME_WRITER_H_
#define EKLT_REBUILD_RECONSTRUCTED_FRAME_WRITER_H_

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <vector>

namespace eklt_rebuild
{

    /// @brief File-output policy for reconstructed display frames.
    struct SReconstructedFrameWriterConfig
    {
        /// @brief Destination directory; an empty path disables persistence.
        std::filesystem::path output_directory;
        /// @brief Save every Nth unique reconstructed frame.
        std::size_t stride{1U};
        /// @brief Maximum saved files, or zero for no explicit limit.
        std::size_t maximum_count{0U};
        /// @brief OpenCV PNG compression level in `[0, 9]`.
        int png_compression{3};
    };

    /// @brief Persist bounded timestamped reconstructed frames as PNG files.
    class CReconstructedFrameWriter
    {
      public:
        /// @brief Validate policy and prepare the explicitly enabled directory.
        /// @param config Output directory and bounded persistence policy.
        /// @throws std::invalid_argument When the configured policy is invalid.
        /// @throws std::runtime_error When the output directory cannot be prepared.
        explicit CReconstructedFrameWriter(const SReconstructedFrameWriterConfig &config);

        /// @brief Process one normalized contiguous `mono8` reconstruction.
        /// @param pixels Row-major image bytes.
        /// @param width Image width in pixels.
        /// @param height Image height in pixels.
        /// @param t_us Absolute reconstruction timestamp in microseconds.
        /// @return True when a PNG was written.
        /// @throws std::invalid_argument When enabled input storage is invalid.
        /// @throws std::runtime_error When encoding or atomic publication fails.
        bool write(const std::vector<uint8_t> &pixels,
                   int width,
                   int height,
                   int64_t t_us);

        /// @brief Check whether persistence is enabled.
        /// @return True when an output directory was configured.
        bool enabled() const;

        /// @brief Return the number of successfully published PNG files.
        /// @return Saved file count.
        std::size_t savedCount() const;

        /// @brief Return the configured output directory.
        /// @return Normalized destination path, or empty when disabled.
        const std::filesystem::path &outputDirectory() const;

      private:
        /// @brief Immutable validated persistence policy.
        SReconstructedFrameWriterConfig config_;
        /// @brief Number of distinct reconstruction timestamps observed.
        std::size_t unique_frame_count_{0U};
        /// @brief Number of PNG files atomically published.
        std::size_t saved_count_{0U};
        /// @brief Last processed reconstruction timestamp.
        int64_t last_t_us_{-1};
    };

} // namespace eklt_rebuild

#endif // EKLT_REBUILD_RECONSTRUCTED_FRAME_WRITER_H_
