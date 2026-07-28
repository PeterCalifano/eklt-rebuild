/// @file event_packet_decoder.h
/// @brief Declares the ROS2 EventPacket-to-native-event adapter.
/// @details The adapter owns codec state and converts transport polarity and
///          nanosecond timestamps into the signed, microsecond native EKLT
///          contract. Tracking and reconstruction remain in the ROS-free
///          orchestrator.

#ifndef EKLT_REBUILD_EVENT_PACKET_DECODER_H_
#define EKLT_REBUILD_EVENT_PACKET_DECODER_H_

#include <cstddef>
#include <cstdint>
#include <vector>

#include <event_camera_codecs/decoder_factory.h>
#include <event_camera_codecs/event_processor.h>
#include <event_camera_msgs/msg/event_packet.hpp>

#include "eklt_core/photometric_patch_tracker.h"

namespace eklt_rebuild
{

    /// @brief Decode standard ROS2 event-camera packets into native EKLT events.
    /// @details Decoder instances are cached by encoding and geometry so
    ///          stateful camera codecs remain continuous across packets.
    class CEventPacketDecoder final : private event_camera_codecs::EventProcessor
    {
      public:
        /// @brief Construct an empty decoder with no selected wire encoding.
        CEventPacketDecoder() = default;

        /// @brief Decode one complete EventPacket without changing source order.
        /// @param packet Standard encoded event-camera packet.
        /// @return Owning native events with signed polarity and microsecond time.
        /// @throws std::invalid_argument If geometry, payload, or encoding is unsupported.
        std::vector<eklt_core::SEventSample>
        decode(const event_camera_msgs::msg::EventPacket &packet);

      private:
        void eventCD(uint64_t t_ns, uint16_t x, uint16_t y, uint8_t polarity) override;
        bool eventExtTrigger(uint64_t t_ns, uint8_t edge, uint8_t id) override;
        void finished() override;
        void rawData(const char *data, std::size_t size) override;

        event_camera_codecs::DecoderFactory<event_camera_msgs::msg::EventPacket,
                                            event_camera_codecs::EventProcessor>
            decoder_factory_;
        std::vector<eklt_core::SEventSample> decoded_events_;
    };

} // namespace eklt_rebuild

#endif // EKLT_REBUILD_EVENT_PACKET_DECODER_H_
