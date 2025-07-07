# src/sensora_indexer/protocols.py

import struct
import ipaddress
import logging
from . import config


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
    Parses a single raw SNSRADV1 payload into a structured dictionary.
    This is now corrected to match the agent's creation logic.
    """
    try:
        # Check for the prefix at the beginning of the single payload
        if not payload.startswith(config.ADVERTISEMENT_PREFIX):
            return None

        offset = len(config.ADVERTISEMENT_PREFIX)

        # Device ID Type (1 byte)
        device_id_type, = struct.unpack_from('>B', payload, offset); offset += 1
        if device_id_type != 0x01: # SENSORA_DEVICE_ID_TYPE_IPV6_FULL
            logger.warning(f"Unsupported device_id_type received: {device_id_type}")
            return None
        
        # Device ID (16 bytes for IPv6)
        ipv6_bytes = payload[offset : offset + 16]; offset += 16
        ipv6_address = str(ipaddress.IPv6Address(ipv6_bytes))
        
        # Port (2 bytes)
        port, = struct.unpack_from('>H', payload, offset); offset += 2

        # Geohash (length-prefixed)
        geohash_len, = struct.unpack_from('>B', payload, offset); offset += 1
        geohash = payload[offset : offset + geohash_len].decode('ascii'); offset += geohash_len

        # Services (number-prefixed)
        num_services, = struct.unpack_from('>B', payload, offset); offset += 1
        
        services = []
        for _ in range(num_services):
            data_type, = struct.unpack_from('>H', payload, offset); offset += 2
            price_sats, = struct.unpack_from('>I', payload, offset); offset += 4
            services.append({"data_type": data_type, "price_sats": price_sats})

        # Timestamp (4 bytes, as corrected in agent's protocol)
        timestamp, = struct.unpack_from('>Q', payload, offset)

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