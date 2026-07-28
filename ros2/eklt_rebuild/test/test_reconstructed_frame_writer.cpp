/// @file test_reconstructed_frame_writer.cpp
/// @brief Verifies bounded atomic reconstructed-frame PNG persistence.
/// @details Uses disposable directories and decoded PNGs to cover disabled
///          output, timestamp deduplication, limits, and byte preservation.

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/imgcodecs.hpp>

#include "eklt_rebuild/reconstructed_frame_writer.h"

namespace
{

    /// @brief Own one disposable directory for a writer test.
    class CTemporaryDirectory
    {
      public:
        /// @brief Create a unique test directory below the system temporary path.
        CTemporaryDirectory()
        {
            const auto nonce =
                std::chrono::steady_clock::now().time_since_epoch().count();
            path_ = std::filesystem::temp_directory_path() /
                    ("eklt-reconstructed-frame-writer-" + std::to_string(nonce));
            if (!std::filesystem::create_directories(path_))
            {
                throw std::runtime_error("failed to create writer test directory");
            }
        }

        /// @brief Remove the owned test directory and every generated fixture.
        ~CTemporaryDirectory()
        {
            std::error_code ignored_error;
            std::filesystem::remove_all(path_, ignored_error);
        }

        CTemporaryDirectory(const CTemporaryDirectory &) = delete;
        CTemporaryDirectory &operator=(const CTemporaryDirectory &) = delete;

        /// @brief Return the owned directory path.
        /// @return Existing disposable directory.
        const std::filesystem::path &path() const
        {
            return path_;
        }

      private:
        /// @brief Unique disposable directory path.
        std::filesystem::path path_;
    };

    /// @brief Create compact deterministic grayscale image bytes.
    /// @return Twelve row-major pixels for a four-by-three image.
    std::vector<uint8_t> MakePixels()
    {
        return {
            0U, 10U, 20U, 30U,
            40U, 50U, 60U, 70U,
            80U, 90U, 100U, 110U,
        };
    }

    /// @brief Return sorted regular files below one directory.
    /// @param directory Directory to inspect.
    /// @return Sorted file paths.
    std::vector<std::filesystem::path> ListFiles(const std::filesystem::path &directory)
    {
        std::vector<std::filesystem::path> files;
        for (const std::filesystem::directory_entry &entry :
             std::filesystem::directory_iterator(directory))
        {
            if (entry.is_regular_file())
            {
                files.push_back(entry.path());
            }
        }
        std::sort(files.begin(), files.end());
        return files;
    }

} // namespace

TEST(CReconstructedFrameWriter, DisabledOutputRetainsNoFiles)
{
    eklt_rebuild::SReconstructedFrameWriterConfig config;
    eklt_rebuild::CReconstructedFrameWriter writer(config);

    EXPECT_FALSE(writer.enabled());
    EXPECT_FALSE(writer.write(MakePixels(), 4, 3, 100));
    EXPECT_EQ(writer.savedCount(), 0U);
    EXPECT_TRUE(writer.outputDirectory().empty());
}

TEST(CReconstructedFrameWriter, WritesReadableTimestampedPngAtomically)
{
    CTemporaryDirectory temporary_directory;
    eklt_rebuild::SReconstructedFrameWriterConfig config;
    config.output_directory = temporary_directory.path() / "frames";
    eklt_rebuild::CReconstructedFrameWriter writer(config);

    ASSERT_TRUE(writer.write(MakePixels(), 4, 3, 100));
    EXPECT_FALSE(writer.write(MakePixels(), 4, 3, 100));
    ASSERT_EQ(writer.savedCount(), 1U);

    const std::vector<std::filesystem::path> files =
        ListFiles(config.output_directory);
    ASSERT_EQ(files.size(), 1U);
    EXPECT_EQ(files.front().filename(), "frame_000000_t_100.png");
    EXPECT_EQ(files.front().extension(), ".png");

    const cv::Mat decoded = cv::imread(files.front().string(), cv::IMREAD_UNCHANGED);
    ASSERT_FALSE(decoded.empty());
    EXPECT_EQ(decoded.type(), CV_8U);
    EXPECT_EQ(decoded.cols, 4);
    EXPECT_EQ(decoded.rows, 3);
    EXPECT_EQ(decoded.at<uint8_t>(2, 3), 110U);
}

TEST(CReconstructedFrameWriter, AppliesStrideAndMaximumCount)
{
    CTemporaryDirectory temporary_directory;
    eklt_rebuild::SReconstructedFrameWriterConfig config;
    config.output_directory = temporary_directory.path() / "frames";
    config.stride = 2U;
    config.maximum_count = 2U;
    config.png_compression = 9;
    eklt_rebuild::CReconstructedFrameWriter writer(config);

    EXPECT_TRUE(writer.write(MakePixels(), 4, 3, 100));
    EXPECT_FALSE(writer.write(MakePixels(), 4, 3, 101));
    EXPECT_TRUE(writer.write(MakePixels(), 4, 3, 102));
    EXPECT_FALSE(writer.write(MakePixels(), 4, 3, 103));
    EXPECT_FALSE(writer.write(MakePixels(), 4, 3, 104));
    EXPECT_EQ(writer.savedCount(), 2U);
    EXPECT_EQ(ListFiles(config.output_directory).size(), 2U);
}

TEST(CReconstructedFrameWriter, CleansTemporaryOutputAndAllowsRetry)
{
    CTemporaryDirectory temporary_directory;
    eklt_rebuild::SReconstructedFrameWriterConfig config;
    config.output_directory = temporary_directory.path() / "frames";
    eklt_rebuild::CReconstructedFrameWriter writer(config);

    const std::filesystem::path final_path =
        config.output_directory / "frame_000000_t_100.png";
    const std::filesystem::path temporary_path =
        config.output_directory / "frame_000000_t_100.tmp.png";

    // Force publication to fail after encoding by occupying the final path
    // with a directory, then require cleanup and a same-timestamp retry.
    ASSERT_TRUE(std::filesystem::create_directory(final_path));
    EXPECT_THROW(writer.write(MakePixels(), 4, 3, 100), std::runtime_error);
    EXPECT_FALSE(std::filesystem::exists(temporary_path));
    EXPECT_EQ(writer.savedCount(), 0U);

    ASSERT_TRUE(std::filesystem::remove(final_path));
    EXPECT_TRUE(writer.write(MakePixels(), 4, 3, 100));
    EXPECT_EQ(writer.savedCount(), 1U);
}

TEST(CReconstructedFrameWriter, RejectsInvalidPolicyAndFrames)
{
    eklt_rebuild::SReconstructedFrameWriterConfig config;
    config.stride = 0U;
    EXPECT_THROW((void)eklt_rebuild::CReconstructedFrameWriter{config},
                 std::invalid_argument);

    config = eklt_rebuild::SReconstructedFrameWriterConfig();
    config.png_compression = 10;
    EXPECT_THROW((void)eklt_rebuild::CReconstructedFrameWriter{config},
                 std::invalid_argument);

    CTemporaryDirectory temporary_directory;
    config = eklt_rebuild::SReconstructedFrameWriterConfig();
    config.output_directory = temporary_directory.path() / "frames";
    eklt_rebuild::CReconstructedFrameWriter writer(config);
    EXPECT_THROW(writer.write(MakePixels(), 5, 3, 100), std::invalid_argument);
    EXPECT_TRUE(writer.write(MakePixels(), 4, 3, 100));
    EXPECT_THROW(writer.write(MakePixels(), 4, 3, 99), std::invalid_argument);
}
