package com.example.setudisasterapp.core

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest

/**
 * 120-Byte Binary SOS Packet Specification (Kotlin Native Implementation).
 * Byte-exact structure matching the hardware specification:
 * 0-5:   Device_Hash (6B)
 * 6-9:   Timestamp (4B uint32)
 * 10-17: Lat_Lon_Fixed (8B: 4B int32 Lat * 1e7, 4B int32 Lon * 1e7)
 * 18-19: Altitude_Baro (2B int16 in decimeters)
 * 20:    Triage_Bitmask (1B: [2b: Severity][3b: Disaster Type][1b: Trapped][2b: Mobility])
 * 21-22: Demographics (2B: [4b: Adults][4b: Children][4b: Elderly][4b: Critical])
 * 23:    Mesh_Telemetry (1B: [4b: Hop Count][4b: Battery % / 10])
 * 24-25: Medical_Codes (2B uint16 bitflags)
 * 26-117: Compressed_Note (92B UTF-8/Smaz text, null padded)
 * 118-119: CRC16_Checksum (2B CRC-16-CCITT)
 */
object SosPacketCodec {
    const val PACKET_SIZE = 120
    const val COMPRESSED_NOTE_SIZE = 92

    fun calculateCrc16Ccitt(data: ByteArray): Int {
        var crc = 0xFFFF
        for (b in data) {
            crc = crc xor ((b.toInt() and 0xFF) shl 8)
            for (i in 0 until 8) {
                crc = if ((crc and 0x8000) != 0) {
                    ((crc shl 1) xor 0x1021) and 0xFFFF
                } else {
                    (crc shl 1) and 0xFFFF
                }
            }
        }
        return crc
    }

    fun pack(
        deviceId: String,
        timestamp: Long,
        latitude: Double,
        longitude: Double,
        altitudeDecimeters: Short,
        severity: Int,       // 0-3
        disasterType: Int,   // 0-7
        isTrapped: Boolean,
        mobility: Int,       // 0-3
        adults: Int,
        children: Int,
        elderly: Int,
        criticalCases: Int,
        hopCount: Int,
        batteryPct: Int,
        medicalFlags: Int,
        note: String
    ): ByteArray {
        val buffer = ByteBuffer.allocate(PACKET_SIZE).order(ByteOrder.BIG_ENDIAN)

        // 1. Device Hash (6B)
        val md = MessageDigest.getInstance("SHA-256")
        val fullHash = md.digest(deviceId.toByteArray(Charsets.UTF_8))
        buffer.put(fullHash, 0, 6)

        // 2. Timestamp (4B uint32)
        buffer.putInt((timestamp and 0xFFFFFFFFL).toInt())

        // 3. Lat / Lon (8B fixed point * 1e7)
        buffer.putInt((latitude * 1e7).toInt())
        buffer.putInt((longitude * 1e7).toInt())

        // 4. Altitude decimeters (2B int16)
        buffer.putShort(altitudeDecimeters)

        // 5. Triage Bitmask (1B)
        val sevBits = (severity and 0x03) shl 6
        val disBits = (disasterType and 0x07) shl 3
        val trapBit = (if (isTrapped) 1 else 0) shl 2
        val mobBits = (mobility and 0x03)
        buffer.put((sevBits or disBits or trapBit or mobBits).toByte())

        // 6. Demographics (2B)
        val demo1 = ((adults.coerceIn(0, 15) shl 4) or children.coerceIn(0, 15)).toByte()
        val demo2 = ((elderly.coerceIn(0, 15) shl 4) or criticalCases.coerceIn(0, 15)).toByte()
        buffer.put(demo1)
        buffer.put(demo2)

        // 7. Mesh Telemetry (1B)
        val battStep = (batteryPct.coerceIn(0, 100) / 10).coerceIn(0, 10)
        val meshByte = ((hopCount.coerceIn(0, 15) shl 4) or battStep).toByte()
        buffer.put(meshByte)

        // 8. Medical Codes (2B)
        buffer.putShort((medicalFlags and 0xFFFF).toShort())

        // 9. Compressed Note (92B)
        val noteBytes = note.toByteArray(Charsets.UTF_8)
        val noteBuffer = ByteArray(COMPRESSED_NOTE_SIZE)
        val copyLen = minOf(noteBytes.size, COMPRESSED_NOTE_SIZE)
        System.arraycopy(noteBytes, 0, noteBuffer, 0, copyLen)
        buffer.put(noteBuffer)

        // 10. CRC16 Checksum (2B)
        val payload118 = ByteArray(118)
        buffer.position(0)
        buffer.get(payload118)
        val crc = calculateCrc16Ccitt(payload118)
        buffer.putShort(crc.toShort())

        return buffer.array()
    }
}
