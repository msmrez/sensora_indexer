# src/sensora_indexer/protocols.py

import struct
import ipaddress
import logging
from . import config

logger = logging.getLogger(__name__)

def parse_op_return_from_script_hex(script_hex: str) -> bytes | None:
    """
    Parses the data payload from a full OP_RETURN script hex.
    """
    try:
        if script_hex.startswith("006a"):
            script_bytes = bytes.fromhex(script_hex[4:])
        elif script_hex.startswith("6a"):
            script_bytes = bytes.fromhex(script_hex[2:])
        else:
            return None

        if not script_bytes:
            return b''

        opcode = script_bytes[0]
        data_start, length_to_read = 0, 0
        if 0x01 <= opcode <= 0x4b:
            length_to_read = opcode; data_start = 1
        elif opcode == 0x4c:
            if len(script_bytes) < 2: return None
            length_to_read = script_bytes[1]; data_start = 2
        elif opcode == 0x4d:
            if len(script_bytes) < 3: return None
            length_to_read = int.from_bytes(script_bytes[1:3], 'little'); data_start = 3
        elif opcode == 0x4e:
            if len(script_bytes) < 5: return None
            length_to_read = int.from_bytes(script_bytes[1:5], 'little'); data_start = 5
        else:
            return None
        
        if len(script_bytes) < data_start + length_to_read:
            return None
        return script_bytes[data_start : data_start + length_to_read]
    except Exception as e:
        logger.error(f"Error parsing script hex '{script_hex[:20]}...': {e}")
        return None

def parse_advertisement_payload(payload: bytes) -> dict | None:
    """
    Parses a raw SNSRADV1 payload into a structured dictionary.
    """
    try:
        if not payload.startswith(config.ADVERTISEMENT_PREFIX):
            return None

        offset = len(config.ADVERTISEMENT_PREFIX)

        device_id_type, = struct.unpack_from('>B', payload, offset); offset += 1
        if device_id_type != 0x01:
            return None
        
        ipv6_bytes = payload[offset : offset + 16]
        ipv6_address = str(ipaddress.IPv6Address(ipv6_bytes)); offset += 16
        
        port, = struct.unpack_from('>H', payload, offset); offset += 2
        
        geohash_len, = struct.unpack_from('>B', payload, offset); offset += 1
        geohash = payload[offset : offset + geohash_len].decode('ascii'); offset += geohash_len
        
        num_services, = struct.unpack_from('>B', payload, offset); offset += 1
        
        services = []
        for _ in range(num_services):
            data_type, = struct.unpack_from('>H', payload, offset); offset += 2
            price_sats, = struct.unpack_from('>I', payload, offset); offset += 4
            services.append({"data_type": data_type, "price_sats": price_sats})

        # --- FINAL CORRECTION ---
        # The timestamp is a 4-byte unsigned integer (>I).
        timestamp, = struct.unpack_from('>I', payload, offset)
        offset += 4 # We must also advance the offset
        # --- END FINAL CORRECTION ---

        return {
            "protocol": "SNSRADV1",
            "device_id": ipv6_address,
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