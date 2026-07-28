/// @file event_packet_reconstruction_debug.cpp
/// @brief Publishes FIBAR images from standard ROS2 EventPacket input.
/// @details This diagnostic node reuses the production EventPacket adapter but
///          remains independent of EKLT tracking. Its image topic is intended
///          for standard ROS2 tools and is never an algorithm input.

#include <cstdint>
#include <exception>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <event_camera_msgs/msg/event_packet.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>

#include "eklt_rebuild/event_packet_decoder.h"
#include "event_recon_fibar_core/fibar_reconstructor.h"

namespace eklt_rebuild
{
    namespace
    {

        uint32_t ReadUint32Parameter(const rclcpp::Node &node, const char *name)
        {
            const int64_t value = node.get_parameter(name).as_int();
            if (value < 0 ||
                static_cast<uint64_t>(value) >
                    static_cast<uint64_t>(std::numeric_limits<uint32_t>::max()))
            {
                throw std::invalid_argument(std::string(name) + " exceeds uint32 range");
            }
            return static_cast<uint32_t>(value);
        }

    } // namespace

    /// @brief Convert decoded EventPacket batches into display-only FIBAR images.
    class CReconstructionDebugNode final : public rclcpp::Node
    {
      public:
        /// @brief Construct the diagnostic subscriber and image publisher.
        CReconstructionDebugNode() : Node("eklt_rebuild_reconstruction_debug")
        {
            declare_parameter<std::string>("events_topic", "/events");
            declare_parameter<int64_t>("events_qos_depth", 4);
            declare_parameter<std::string>("image_topic", "/event_reconstruction");
            declare_parameter<int64_t>("fibar_cutoff_time_us", 10000);
            declare_parameter<double>("fibar_fill_ratio", 0.5);
            declare_parameter<bool>("fibar_use_spatial_filter", true);

            const std::string image_topic =
                get_parameter("image_topic").as_string();
            image_publisher_ =
                create_publisher<sensor_msgs::msg::Image>(image_topic,
                                                          rclcpp::SensorDataQoS());

            const int64_t qos_depth = get_parameter("events_qos_depth").as_int();
            if (qos_depth <= 0 ||
                static_cast<uint64_t>(qos_depth) >
                    static_cast<uint64_t>(std::numeric_limits<std::size_t>::max()))
            {
                throw std::invalid_argument("events_qos_depth must be a positive size");
            }

            // Match production's bounded sensor-data behavior even though this
            // diagnostic owns no tracking state.
            rclcpp::SensorDataQoS events_qos;
            events_qos.keep_last(static_cast<std::size_t>(qos_depth));
            const std::string events_topic =
                get_parameter("events_topic").as_string();
            const auto packet_callback =
                [this](event_camera_msgs::msg::EventPacket::ConstSharedPtr packet)
                {
                    handlePacket(*packet);
                };
            event_subscription_ =
                create_subscription<event_camera_msgs::msg::EventPacket>(events_topic,
                                                                         events_qos,
                                                                         packet_callback);
        }

      private:
        void handlePacket(const event_camera_msgs::msg::EventPacket &packet)
        {
            try
            {
                const std::vector<eklt_core::SEventSample> events = decoder_.decode(packet);
                if (events.empty())
                {
                    return;
                }

                ensureReconstructor(static_cast<int>(packet.width),
                                    static_cast<int>(packet.height));
                acceptEvents(events);
                const int64_t latest_t_us = events.back().t_us;
                if (reconstructor_->hasImageFor(latest_t_us))
                {
                    publishImage(packet.header, reconstructor_->requestImage(latest_t_us));
                }
            }
            catch (const std::exception &error)
            {
                RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                      "reconstruction packet rejected: %s", error.what());
            }
        }

        void ensureReconstructor(int width, int height)
        {
            if (reconstructor_)
            {
                if (reconstructor_->width() != width || reconstructor_->height() != height)
                {
                    throw std::invalid_argument("EventPacket geometry changed during "
                                                "reconstruction");
                }
                return;
            }

            event_recon_fibar_core::SFibarConfig config;
            config.width = width;
            config.height = height;
            config.cutoff_time_us = ReadUint32Parameter(*this, "fibar_cutoff_time_us");
            config.fill_ratio = get_parameter("fibar_fill_ratio").as_double();
            config.use_spatial_filter = get_parameter("fibar_use_spatial_filter").as_bool();
            reconstructor_ =
                std::make_unique<event_recon_fibar_core::CFibarReconstructor>(config);
        }

        void acceptEvents(const std::vector<eklt_core::SEventSample> &events)
        {
            std::vector<uint16_t> x;
            std::vector<uint16_t> y;
            std::vector<int8_t> polarity;
            std::vector<int64_t> timestamps_us;
            x.reserve(events.size());
            y.reserve(events.size());
            polarity.reserve(events.size());
            timestamps_us.reserve(events.size());
            for (const eklt_core::SEventSample &event : events)
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
                reconstructor_->width(),
                reconstructor_->height(),
            };
            reconstructor_->acceptEvents(batch);
        }

        void publishImage(const std_msgs::msg::Header &header,
                          const event_recon_fibar_core::SReconstructedImageView &image)
        {
            sensor_msgs::msg::Image message;
            message.header = header;
            message.height = static_cast<uint32_t>(image.height);
            message.width = static_cast<uint32_t>(image.width);
            message.encoding = "mono8";
            message.is_bigendian = false;
            message.step = static_cast<sensor_msgs::msg::Image::_step_type>(image.width);
            message.data =
                event_recon_fibar_core::NormalizeImageForDisplay(image.data, image.size);
            image_publisher_->publish(message);
        }

        CEventPacketDecoder decoder_;
        std::unique_ptr<event_recon_fibar_core::CFibarReconstructor> reconstructor_;
        rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr image_publisher_;
        rclcpp::Subscription<event_camera_msgs::msg::EventPacket>::SharedPtr
            event_subscription_;
    };

} // namespace eklt_rebuild

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    try
    {
        rclcpp::spin(std::make_shared<eklt_rebuild::CReconstructionDebugNode>());
    }
    catch (const std::exception &error)
    {
        RCLCPP_FATAL(rclcpp::get_logger("eklt_rebuild_reconstruction_debug"),
                     "%s", error.what());
        rclcpp::shutdown();
        return 1;
    }
    rclcpp::shutdown();
    return 0;
}
