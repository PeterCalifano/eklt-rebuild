/// @file event_packet_decoder.cpp
/// @brief Implements standard ROS2 EventPacket decoding for native EKLT input.
/// @details The implementation deliberately contains no tracking policy; it
///          validates transport shape and delegates every supported encoding
///          to event_camera_codecs.

#include "eklt_rebuild/event_packet_decoder.h"

#include <limits>
#include <stdexcept>
#include <string>

namespace eklt_rebuild
{

    std::vector<eklt_core::SEventSample>
    CEventPacketDecoder::decode(const event_camera_msgs::msg::EventPacket &packet)
    {
        if (packet.width == 0U || packet.height == 0U ||
            packet.width > static_cast<uint32_t>(std::numeric_limits<uint16_t>::max()) ||
            packet.height > static_cast<uint32_t>(std::numeric_limits<uint16_t>::max()))
        {
            throw std::invalid_argument("EventPacket geometry exceeds codec limits");
        }
        if (packet.encoding == "mono" && packet.events.size() % 8U != 0U)
        {
            throw std::invalid_argument("mono EventPacket payload must contain complete events");
        }

        event_camera_codecs::Decoder<event_camera_msgs::msg::EventPacket,
                                     event_camera_codecs::EventProcessor> *decoder =
            decoder_factory_.getInstance(packet);
        if (decoder == nullptr)
        {
            throw std::invalid_argument("unsupported EventPacket encoding: " + packet.encoding);
        }

        // Decode into private working storage so a codec failure cannot expose
        // a partial batch to the native all-or-nothing acceptance boundary.
        decoded_events_.clear();
        try
        {
            while (decoder->decode(packet, this))
            {
            }
        }
        catch (...)
        {
            decoded_events_.clear();
            throw;
        }

        std::vector<eklt_core::SEventSample> output;
        output.swap(decoded_events_);
        return output;
    }

    void CEventPacketDecoder::eventCD(uint64_t t_ns, uint16_t x, uint16_t y, uint8_t polarity)
    {
        decoded_events_.push_back(eklt_core::SEventSample{
            x,
            y,
            static_cast<int8_t>(polarity == 0U ? -1 : 1),
            static_cast<int64_t>(t_ns / 1000U),
        });
    }

    bool CEventPacketDecoder::eventExtTrigger(uint64_t, uint8_t, uint8_t)
    {
        return true;
    }

    void CEventPacketDecoder::finished()
    {
    }

    void CEventPacketDecoder::rawData(const char *, std::size_t)
    {
    }

} // namespace eklt_rebuild
