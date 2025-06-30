# sensora_indexer/protocols.py

import struct
import ipaddress
import logging
from . import config

logger = logging.getLogger(__name__)

def parse_op_return_from_script_hex(script_hex: str) -> bytes | None:
    """
    Parses the data payload from a full OP_RETURN script hex.
    Returns the raw data bytes, or None if not a valid OP_RETURN.
    """
    try:
        if script_hex.startswith("006a"): # OP_FALSE OP_RETURN
            script_bytes = bytes.fromhex(script_hex[4:])
        elif script_hex.startswith("6a"): # OP_RETURN
            script_bytes = bytes.fromhex(script_hex[2:])
        else:
            return None

        if not script_bytes:
            return b''

        opcode = script_bytes[0]
        if 0x01 <= opcode <= 0x4b:
            length_to_read = opcode
            if len(script_bytes) < 1 + length_to_read: return None
            return script_bytes[1 : 1 + length_to_read]
        elif opcode == 0x4c:
            if len(script_bytes) < 2: return None
            length_to_read = script_bytes[1]
            if len(script_bytes) < 2 + length_to_read: return None
            return script_bytes[2 : 2 + length_to_read]
        # Add PUSHDATA2/4 if you expect larger payloads, otherwise this is fine
        
        return None # Not a simple pushdata script
    except Exception as e:
        logger.error(f"Error parsing script hex '{script_hex[:20]}...': {e}")
        return None

def parse_advertisement_payload(payload: bytes) -> dict | None:
    """
    Parses a raw SNSRADV1 payload into a structured dictionary.
    """
    try:
        if not payload.startswith(config.ADVERTISEMENT_PREFIX):
            return None # Not our advertisement protocol

        offset = len(config.ADVERTISEMENT_PREFIX)

        # Device ID Type (1 byte)
        device_id_type, = struct.unpack_from('>B', payload, offset)
        offset += 1

        # Device ID (e.g., 16 bytes for IPv6)
        # For now, we only support full IPv6
        if device_id_type != 0x01:
            logger.warning(f"Unsupported device_id_type received: {device_id_type}")
            return None
        
        ipv6_bytes = payload[offset : offset + 16]
        ipv6_address = str(ipaddress.IPv6Address(ipv6_bytes))
        offset += 16
        
        # Port (2 bytes)
        port, = struct.unpack_from('>H', payload, offset)
        offset += 2

        # Geohash (length-prefixed)
        geohash_len, = struct.unpack_from('>B', payload, offset)
        offset += 1
        geohash = payload[offset : offset + geohash_len].decode('ascii')
        offset += geohash_len

        # Services (number-prefixed)
        num_services, = struct.unpack_from('>B', payload, offset)
        offset += 1
        
        services = []
        for _ in range(num_services):
            data_type, = struct.unpack_from('>H', payload, offset)
            offset += 2
            price_sats, = struct.unpack_from('>I', payload, offset)
            offset += 4
            services.append({"data_type": data_type, "price_sats": price_sats})

        # Timestamp (8 bytes)
        timestamp, = struct.unpack_from('>Q', payload, offset)

        return {
            "protocol": "SNSRADV1",
            "device_id": ipv6_address, # Use IPv6 as the unique device ID
            "ipv6_address": ipv6_address,
            "port": port,
            "geohash": geohash,
            "services": services,
            "timestamp": timestamp,
        }

    except (struct.error, IndexError, UnicodeDecodeError) as e:
        logger.error(f"Failed to parse SNSRADV1 payload due to structural error: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error parsing SNSRADV1 payload: {e}")
        return None