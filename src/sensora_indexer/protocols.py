# src/sensora_indexer/protocols.py

import struct
import ipaddress
import logging
from . import config
import json


logger = logging.getLogger(__name__)

def parse_op_return_from_script_hex(script_hex: str) -> bytes | None:
    """
    Parses the data payload from a full OP_RETURN script hex.
    This simplified version correctly handles 'OP_FALSE OP_RETURN' scripts.
    """
    try:
        # Standard OP_FALSE OP_RETURN
        if script_hex.startswith('006a'):
            # The script is: 006a <pushdata_opcode> <data>
            # We need to skip the opcodes to get to the data.
            script_bytes = bytes.fromhex(script_hex)
            
            # The byte at index 2 is the pushdata opcode.
            # 0x01-0x4b: pushdata is the opcode value itself. data starts at index 3.
            # 0x4c: next byte is length. data starts at index 4.
            # 0x4d: next 2 bytes are length. data starts at index 5.
            opcode = script_bytes[2]
            if 0x01 <= opcode <= 0x4b:
                return script_bytes[3:]
            elif opcode == 0x4c:
                return script_bytes[4:]
            elif opcode == 0x4d:
                return script_bytes[5:]
            else: # Not a simple push, or an unsupported one.
                return None

        # Standard OP_RETURN
        elif script_hex.startswith('6a'):
             # The script is: 6a <pushdata_opcode> <data>
            script_bytes = bytes.fromhex(script_hex)
            opcode = script_bytes[1]
            if 0x01 <= opcode <= 0x4b:
                return script_bytes[2:]
            elif opcode == 0x4c:
                return script_bytes[3:]
            elif opcode == 0x4d:
                return script_bytes[4:]
            else:
                return None
                
        return None

    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing OP_RETURN hex '{script_hex[:30]}...': {e}")
        return None


def parse_advertisement_payload(payload: bytes) -> dict | None:
    """
    Parses a raw SENSORA_ADV payload with the new JSON services format.
    """
    try:
        if not payload.startswith(config.SENSORA_ADV_PREFIX):
            return None

        # Deconstruct the payload according to the new format
        offset = len(config.SENSORA_ADV_PREFIX)

        device_id_type, = struct.unpack_from('>B', payload, offset); offset += 1
        if device_id_type != 0x01: return None
        ipv6_bytes = payload[offset : offset + 16]; offset += 16
        ipv6_address = str(ipaddress.IPv6Address(ipv6_bytes))
        
        port, = struct.unpack_from('>H', payload, offset); offset += 2

        geohash_len, = struct.unpack_from('>B', payload, offset); offset += 1
        geohash = payload[offset : offset + geohash_len].decode('ascii'); offset += geohash_len

        # The rest of the payload up to the final 8-byte timestamp is the services JSON
        timestamp_size = 8
        services_json_bytes = payload[offset:-timestamp_size]
        
        try:
            # Decode the bytes to a string, then load the JSON.
            services_list = json.loads(services_json_bytes.decode('utf-8'))
            if not isinstance(services_list, list):
                # If it's not a list, something is wrong. Default to empty.
                services_list = []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Could not parse services JSON for sensor {ipv6_address}:{port}. Error: {e}")
            logger.debug(f"Problematic JSON bytes: {services_json_bytes}")
            services_list = []
        # The timestamp is the last 8 bytes
        timestamp, = struct.unpack_from('>Q', payload, -timestamp_size)
        return {
            "protocol": "SENSORA_ADV_JSON_V1",
            "device_id": ipv6_address,
            "ipv6_address": ipv6_address, # <-- ADD THIS MISSING KEY
            "port": port,
            "geohash": geohash,
            "services": services_list,
            "timestamp": timestamp,
        }

    except (struct.error, IndexError) as e:
        logger.error(f"Failed to parse advertisement payload due to structural error: {e}")
        return None