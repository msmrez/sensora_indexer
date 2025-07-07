# src/sensora_indexer/protocols.py

import struct, ipaddress, logging
from . import config
logger = logging.getLogger(__name__)

def get_all_op_return_pushes(script_hex: str) -> list[bytes] | None:
    """Manually parses a script and returns a list of all data pushes."""
    try:
        if script_hex.startswith("006a"): script_bytes = bytes.fromhex(script_hex[4:])
        elif script_hex.startswith("6a"): script_bytes = bytes.fromhex(script_hex[2:])
        else: return None
        
        pushes = []
        offset = 0
        while offset < len(script_bytes):
            opcode = script_bytes[offset]
            offset += 1
            length_to_read = 0
            if 1 <= opcode <= 75: length_to_read = opcode
            elif opcode == 76:
                if offset >= len(script_bytes): break
                length_to_read = script_bytes[offset]; offset += 1
            elif opcode == 77:
                if offset + 1 >= len(script_bytes): break
                length_to_read = int.from_bytes(script_bytes[offset:offset+2], 'little'); offset += 2
            else: break # Not a push opcode we handle
            
            data_push = script_bytes[offset : offset + length_to_read]
            pushes.append(data_push)
            offset += length_to_read
        return pushes
    except Exception as e:
        logger.exception(f"Error parsing all op_return pushes: {e}")
        return None

def parse_advertisement_from_pushes(pushes: list[bytes]) -> dict | None:
    """Parses an advertisement from a list of data pushes."""
    try:
        # pushes[0] is the prefix, which we already checked.
        # Let's assume the full payload is in the second push.
        payload = pushes[1] 

        offset = 0
        device_id_type, = struct.unpack_from('>B', payload, offset); offset += 1
        if device_id_type != 0x01: return None
        
        ipv6_bytes = payload[offset : offset + 16]; offset += 16
        ipv6_address = str(ipaddress.IPv6Address(ipv6_bytes))
        
        port, = struct.unpack_from('>H', payload, offset); offset += 2
        geohash_len, = struct.unpack_from('>B', payload, offset); offset += 1
        geohash = payload[offset : offset + geohash_len].decode('ascii'); offset += geohash_len
        num_services, = struct.unpack_from('>B', payload, offset); offset += 1
        
        services = []
        for _ in range(num_services):
            data_type, = struct.unpack_from('>H', payload, offset); offset += 2
            price_sats, = struct.unpack_from('>I', payload, offset); offset += 4
            services.append({"data_type": data_type, "price_sats": price_sats})

        timestamp, = struct.unpack_from('>I', payload, offset)

        return {"device_id": ipv6_address, "ipv6_address": ipv6_address, "port": port, "geohash": geohash, "services": services, "timestamp": timestamp}
    except Exception as e:
        logger.exception(f"Error parsing advertisement from pushes: {e}")
        return None