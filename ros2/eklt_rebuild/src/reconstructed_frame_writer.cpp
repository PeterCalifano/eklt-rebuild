/// @file reconstructed_frame_writer.cpp
/// @brief Implements bounded atomic PNG reconstruction persistence.
/// @details Each selected `mono8` frame is encoded independently and no pixel
///          history is retained after the write returns.

#include "eklt_rebuild/reconstructed_frame_writer.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

#include <opencv2/imgcodecs.hpp>

namespace eklt_rebuild
{
    namespace
    {

        /// @brief Build a deterministic timestamped output filename.
        /// @param index Zero-based saved-frame index.
        /// @param t_us Absolute reconstruction timestamp.
        /// @return Basename ending in `.png`.
        std::string MakeFrameFilename(std::size_t index, int64_t t_us)
        {
            std::ostringstream filename;
            filename << "frame_" << std::setfill('0') << std::setw(6) << index
                     << "_t_" << t_us << ".png";
            return filename.str();
        }

        /// @brief Remove one temporary file without obscuring the primary error.
        /// @param path Temporary sibling path.
        void RemoveTemporaryFile(const std::filesystem::path &path)
        {
            std::error_code ignored_error;
            std::filesystem::remove(path, ignored_error);
        }

    } // namespace

    CReconstructedFrameWriter::CReconstructedFrameWriter(const SReconstructedFrameWriterConfig &config)
        : config_(config)
    {
        if (config_.stride == 0U)
        {
            throw std::invalid_argument("reconstructed-frame stride must be positive");
        }
        if (config_.png_compression < 0 || config_.png_compression > 9)
        {
            throw std::invalid_argument("PNG compression must be between zero and nine");
        }
        if (!enabled())
        {
            return;
        }

        config_.output_directory = config_.output_directory.lexically_normal();
        if (config_.output_directory == config_.output_directory.root_path())
        {
            throw std::invalid_argument("reconstructed-frame output cannot be a filesystem root");
        }

        // Prepare only the explicitly configured leaf directory and reject a
        // non-directory collision before processing any image data.
        std::error_code error;
        std::filesystem::create_directories(config_.output_directory, error);
        if (error)
        {
            throw std::runtime_error("failed to create reconstructed-frame directory: " +
                                     error.message());
        }
        if (!std::filesystem::is_directory(config_.output_directory, error) || error)
        {
            throw std::runtime_error("reconstructed-frame output is not a directory");
        }
    }

    bool CReconstructedFrameWriter::write(const std::vector<uint8_t> &pixels,
                                           int width,
                                           int height,
                                           int64_t t_us)
    {
        if (!enabled())
        {
            return false;
        }
        if (width <= 0 || height <= 0 || t_us < 0)
        {
            throw std::invalid_argument("reconstructed frame metadata is invalid");
        }
        if (static_cast<std::size_t>(width) >
            std::numeric_limits<std::size_t>::max() /
                static_cast<std::size_t>(height))
        {
            throw std::invalid_argument("reconstructed frame geometry overflows storage");
        }
        const std::size_t expected_size =
            static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
        if (pixels.size() != expected_size)
        {
            throw std::invalid_argument("reconstructed frame byte count is invalid");
        }
        if (t_us == last_t_us_)
        {
            return false;
        }
        if (last_t_us_ >= 0 && t_us < last_t_us_)
        {
            throw std::invalid_argument("reconstructed frame timestamps regressed");
        }

        const std::size_t unique_index = unique_frame_count_;
        if (unique_index % config_.stride != 0U ||
            (config_.maximum_count > 0U && saved_count_ >= config_.maximum_count))
        {
            last_t_us_ = t_us;
            ++unique_frame_count_;
            return false;
        }

        const std::filesystem::path final_path =
            config_.output_directory / MakeFrameFilename(saved_count_, t_us);
        const std::filesystem::path temporary_path =
            final_path.parent_path() /
            (final_path.stem().string() + ".tmp.png");

        // Encode to a temporary sibling first so interrupted demos never leave
        // a final filename backed by a partial PNG stream.
        const cv::Mat image(height, width, CV_8U,
                            const_cast<uint8_t *>(pixels.data()));
        const std::vector<int> parameters = {
            cv::IMWRITE_PNG_COMPRESSION,
            config_.png_compression,
        };
        try
        {
            if (!cv::imwrite(temporary_path.string(), image, parameters))
            {
                RemoveTemporaryFile(temporary_path);
                throw std::runtime_error("OpenCV did not encode reconstructed-frame PNG");
            }
        }
        catch (const cv::Exception &error)
        {
            RemoveTemporaryFile(temporary_path);
            throw std::runtime_error("failed to encode reconstructed-frame PNG: " +
                                     std::string(error.what()));
        }

        // POSIX rename replaces an existing regular file atomically, avoiding
        // a window in which a previous final frame has been removed.
        std::error_code error;
        std::filesystem::rename(temporary_path, final_path, error);
        if (error)
        {
            RemoveTemporaryFile(temporary_path);
            throw std::runtime_error("failed to publish reconstructed-frame PNG: " +
                                     error.message());
        }

        // Advance timestamp and stride state only after a selected frame is
        // durable, allowing the caller to retry the same timestamp on failure.
        last_t_us_ = t_us;
        ++unique_frame_count_;
        ++saved_count_;
        return true;
    }

    bool CReconstructedFrameWriter::enabled() const
    {
        return !config_.output_directory.empty();
    }

    std::size_t CReconstructedFrameWriter::savedCount() const
    {
        return saved_count_;
    }

    const std::filesystem::path &CReconstructedFrameWriter::outputDirectory() const
    {
        return config_.output_directory;
    }

} // namespace eklt_rebuild
