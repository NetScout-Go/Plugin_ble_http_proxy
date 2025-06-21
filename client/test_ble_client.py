#!/usr/bin/env python3
"""
NetTool BLE HTTP Proxy Client
This script provides a client for the NetTool BLE HTTP Proxy service.
It can be used to test the BLE connection and send HTTP requests.
"""

import argparse
import binascii
import logging
import sys
import time
import uuid

try:
    from bluepy import btle
except ImportError:
    print("Error: bluepy module not found. Install with 'pip install bluepy'")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('nettool-ble-client')

# BLE Service UUIDs
BLE_SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
BLE_REQUEST_CHAR_UUID = "00001235-0000-1000-8000-00805f9b34fb"
BLE_RESPONSE_CHAR_UUID = "00001236-0000-1000-8000-00805f9b34fb"
BLE_STATUS_CHAR_UUID = "00001237-0000-1000-8000-00805f9b34fb"

class NotificationDelegate(btle.DefaultDelegate):
    def __init__(self):
        btle.DefaultDelegate.__init__(self)
        self.response_data = bytearray()
        self.response_complete = False
        self.current_uuid = None
    
    def handleNotification(self, cHandle, data):
        if len(data) < 17:  # Minimum length: UUID (16) + flags (1)
            logger.error("Received notification with invalid length")
            return
        
        # Extract UUID and flags
        uuid_bytes = data[:16]
        flags = data[16]
        chunk_data = data[17:]
        
        # Clean up UUID (remove trailing nulls)
        uuid_str = uuid_bytes.decode('utf-8').rstrip('\0')
        
        is_first = (flags & 1) != 0
        is_last = (flags & 2) != 0
        
        logger.debug(f"Received chunk: UUID={uuid_str}, first={is_first}, last={is_last}, len={len(chunk_data)}")
        
        if is_first:
            # New response
            self.response_data = bytearray(chunk_data)
            self.current_uuid = uuid_str
        elif uuid_str == self.current_uuid:
            # Continuation of previous response
            self.response_data.extend(chunk_data)
        else:
            logger.error(f"Received chunk for unexpected UUID: {uuid_str}")
            return
        
        if is_last:
            self.response_complete = True
            logger.info(f"Response complete: {len(self.response_data)} bytes")

def scan_for_devices(timeout=10):
    """Scan for BLE devices"""
    logger.info(f"Scanning for BLE devices for {timeout} seconds...")
    scanner = btle.Scanner()
    devices = scanner.scan(timeout)
    
    logger.info(f"Found {len(devices)} devices")
    for dev in devices:
        logger.info(f"Device {dev.addr} ({dev.addrType}), RSSI={dev.rssi} dB")
        for (adtype, desc, value) in dev.getScanData():
            if desc == "Complete Local Name" and "NetTool" in value:
                logger.info(f"  {desc}: {value} ** NETTOOL DEVICE **")
            else:
                logger.info(f"  {desc}: {value}")
    
    return devices

def connect_to_device(address):
    """Connect to a specific device by MAC address"""
    try:
        logger.info(f"Connecting to {address}...")
        peripheral = btle.Peripheral(address)
        peripheral.setDelegate(NotificationDelegate())
        
        # Get service
        service = peripheral.getServiceByUUID(BLE_SERVICE_UUID)
        
        # Get characteristics
        request_char = service.getCharacteristic(BLE_REQUEST_CHAR_UUID)
        response_char = service.getCharacteristic(BLE_RESPONSE_CHAR_UUID)
        status_char = service.getCharacteristic(BLE_STATUS_CHAR_UUID)
        
        # Enable notifications for response characteristic
        response_desc = response_char.getDescriptors(forUUID=0x2902)[0]
        response_desc.write(b"\x01\x00", True)
        
        return peripheral
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return None

def get_status(peripheral):
    """Get status information from the BLE HTTP Proxy"""
    try:
        service = peripheral.getServiceByUUID(BLE_SERVICE_UUID)
        status_char = service.getCharacteristic(BLE_STATUS_CHAR_UUID)
        
        status_bytes = status_char.read()
        status_str = bytes(status_bytes).decode('utf-8')
        
        import json
        status_json = json.loads(status_str)
        
        logger.info(f"Status: {status_json}")
        return status_json
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return None

def send_http_request(peripheral, method, path, headers=None, body=None):
    """Send an HTTP request over BLE"""
    try:
        service = peripheral.getServiceByUUID(BLE_SERVICE_UUID)
        request_char = service.getCharacteristic(BLE_REQUEST_CHAR_UUID)
        response_char = service.getCharacteristic(BLE_RESPONSE_CHAR_UUID)
        
        # Build HTTP request
        request = f"{method} {path} HTTP/1.1\r\n"
        
        # Add headers
        if headers is None:
            headers = {}
        
        for key, value in headers.items():
            request += f"{key}: {value}\r\n"
        
        # Add content length if body is provided
        if body:
            request += f"Content-Length: {len(body)}\r\n"
        
        # End headers
        request += "\r\n"
        
        # Add body if provided
        if body:
            request += body
        
        logger.info(f"Sending HTTP request: {method} {path}")
        
        # Generate a random request ID
        request_id = str(uuid.uuid4())[:16]
        request_bytes = request.encode('utf-8')
        
        # Maximum data size per write
        max_chunk_size = 512 - 17  # 16 bytes for UUID, 1 byte for flags
        
        # Calculate number of chunks
        total_chunks = (len(request_bytes) + max_chunk_size - 1) // max_chunk_size
        
        delegate = peripheral.delegate
        delegate.response_complete = False
        delegate.response_data = bytearray()
        delegate.current_uuid = request_id
        
        for i in range(total_chunks):
            start = i * max_chunk_size
            end = min(start + max_chunk_size, len(request_bytes))
            
            # Create flags: bit 0 = first chunk, bit 1 = last chunk
            flags = 0
            if i == 0:
                flags |= 1  # First chunk
            if i == total_chunks - 1:
                flags |= 2  # Last chunk
            
            # Prepare chunk with request ID and flags
            chunk = bytearray(request_id.encode('utf-8'))
            # Pad to 16 bytes
            chunk.extend(b'\0' * (16 - len(chunk)))
            chunk.append(flags)
            chunk.extend(request_bytes[start:end])
            
            # Send chunk
            request_char.write(chunk, withResponse=True)
            
            logger.debug(f"Sent chunk {i+1}/{total_chunks}: {len(chunk)} bytes")
        
        # Wait for response
        start_time = time.time()
        timeout = 30  # 30 seconds timeout
        
        while not delegate.response_complete and time.time() - start_time < timeout:
            if peripheral.waitForNotifications(1.0):
                continue
        
        if not delegate.response_complete:
            logger.error("Timeout waiting for response")
            return None
        
        # Parse HTTP response
        response_data = bytes(delegate.response_data)
        
        # Find the end of headers
        header_end = response_data.find(b'\r\n\r\n')
        if header_end < 0:
            logger.error("Invalid HTTP response: no header separator found")
            return None
        
        headers_data = response_data[:header_end].decode('utf-8')
        body_data = response_data[header_end + 4:]
        
        headers_lines = headers_data.split('\r\n')
        status_line = headers_lines[0]
        headers = {}
        
        for line in headers_lines[1:]:
            if not line:
                continue
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
        
        response = {
            'status_line': status_line,
            'headers': headers,
            'body': body_data
        }
        
        try:
            http_version, status_code, reason = status_line.split(' ', 2)
            response['status_code'] = int(status_code)
            response['reason'] = reason
        except:
            logger.warning(f"Could not parse status line: {status_line}")
        
        logger.info(f"Received response: {status_line}")
        logger.info(f"Body size: {len(body_data)} bytes")
        
        return response
    except Exception as e:
        logger.error(f"Failed to send HTTP request: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    parser = argparse.ArgumentParser(description='NetTool BLE HTTP Proxy Client')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scan', action='store_true', help='Scan for BLE devices')
    group.add_argument('--connect', type=str, help='Connect to a specific device by MAC address')
    group.add_argument('--status', type=str, help='Get status from a specific device')
    group.add_argument('--get', type=str, help='Send GET request to a specific device')
    
    parser.add_argument('--path', type=str, default='/', help='HTTP path for request (default: /)')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout in seconds (default: 10)')
    
    args = parser.parse_args()
    
    if args.scan:
        scan_for_devices(args.timeout)
        return
    
    if args.connect:
        peripheral = connect_to_device(args.connect)
        if peripheral:
            logger.info("Successfully connected to device")
            peripheral.disconnect()
        return
    
    if args.status:
        peripheral = connect_to_device(args.status)
        if peripheral:
            get_status(peripheral)
            peripheral.disconnect()
        return
    
    if args.get:
        peripheral = connect_to_device(args.get)
        if peripheral:
            response = send_http_request(peripheral, 'GET', args.path)
            if response and 'body' in response:
                try:
                    body_text = response['body'].decode('utf-8')
                    print("\nResponse body:")
                    print(body_text[:1000])  # Print first 1000 chars
                    if len(body_text) > 1000:
                        print("... (truncated)")
                except:
                    print("\nResponse body: (binary data)")
            peripheral.disconnect()
        return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
