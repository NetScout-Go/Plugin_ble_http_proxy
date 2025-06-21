#!/usr/bin/env python3
"""
NetTool BLE HTTP Proxy Service
This script implements a Bluetooth Low Energy GATT server that proxies HTTP requests
to the local NetTool HTTP server and returns the responses over BLE.
"""

import argparse
import asyncio
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import http.client
import logging
import os
import signal
import socket
import struct
import sys
import time
import threading
import uuid
from gi.repository import GLib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/tmp/nettool_ble_proxy.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('nettool-ble-proxy')

# BLE Service UUIDs
BLE_HTTP_PROXY_SERVICE_UUID = '00001234-0000-1000-8000-00805f9b34fb'
BLE_HTTP_REQUEST_CHAR_UUID = '00001235-0000-1000-8000-00805f9b34fb'
BLE_HTTP_RESPONSE_CHAR_UUID = '00001236-0000-1000-8000-00805f9b34fb'
BLE_STATUS_CHAR_UUID = '00001237-0000-1000-8000-00805f9b34fb'

# BlueZ D-Bus constants
BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'
GATT_MANAGER_INTERFACE = 'org.bluez.GattManager1'
GATT_SERVICE_INTERFACE = 'org.bluez.GattService1'
GATT_CHARACTERISTIC_INTERFACE = 'org.bluez.GattCharacteristic1'
DBUS_OM_INTERFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_INTERFACE = 'org.freedesktop.DBus.Properties'
LE_ADVERTISING_MANAGER_INTERFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_INTERFACE = 'org.bluez.LEAdvertisement1'

# Status file for storing the BLE proxy state
STATUS_FILE = '/tmp/nettool_ble_proxy.status'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'

class HTTPRequest:
    """Represents an HTTP request received over BLE"""
    def __init__(self, request_id):
        self.request_id = request_id
        self.data = bytearray()
        self.complete = False
    
    def add_chunk(self, chunk, is_first, is_last):
        self.data.extend(chunk)
        if is_last:
            self.complete = True
    
    def parse(self):
        """Parse the HTTP request into method, path, headers, and body"""
        try:
            request_str = self.data.decode('utf-8')
            lines = request_str.split('\r\n')
            
            # Parse request line
            method, path, _ = lines[0].split(' ')
            
            # Parse headers
            headers = {}
            body_start = 0
            for i, line in enumerate(lines[1:], 1):
                if not line:
                    body_start = i + 1
                    break
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            
            # Get body if present
            body = '\r\n'.join(lines[body_start:]) if body_start < len(lines) else ''
            
            return {
                'method': method,
                'path': path,
                'headers': headers,
                'body': body
            }
        except Exception as e:
            logger.error(f"Error parsing HTTP request: {e}")
            return None

class Advertisement(dbus.service.Object):
    """BLE Advertisement object for the HTTP Proxy service"""
    def __init__(self, bus, index, advertising_type, device_name):
        self.path = f"/org/bluez/example/advertisement{index}"
        self.bus = bus
        self.ad_type = advertising_type
        self.device_name = device_name
        self.service_uuids = [BLE_HTTP_PROXY_SERVICE_UUID]
        self.manufacturer_data = {}
        self.solicit_uuids = []
        self.service_data = {}
        self.include_tx_power = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        if len(self.solicit_uuids) > 0:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids, signature='s')
        if len(self.manufacturer_data) > 0:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if len(self.service_data) > 0:
            properties['ServiceData'] = dbus.Dictionary(self.service_data, signature='sv')
        if self.include_tx_power:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.device_name:
            properties['LocalName'] = dbus.String(self.device_name)
        return {LE_ADVERTISEMENT_INTERFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_INTERFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_INTERFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_INTERFACE]

    @dbus.service.method(LE_ADVERTISEMENT_INTERFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        logger.info('%s: Released' % self.path)

class HTTPProxyService(dbus.service.Object):
    """GATT Service for HTTP Proxying"""
    def __init__(self, bus, index, http_port):
        self.path = f"/org/bluez/example/service{index}"
        self.bus = bus
        self.http_port = http_port
        self.pending_requests = {}
        self.next_response_handle = 1
        
        dbus.service.Object.__init__(self, bus, self.path)
        
        self.add_request_characteristic()
        self.add_response_characteristic()
        self.add_status_characteristic()
    
    def get_properties(self):
        return {
            GATT_SERVICE_INTERFACE: {
                'UUID': BLE_HTTP_PROXY_SERVICE_UUID,
                'Primary': True,
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_INTERFACE,
                        in_signature='s',
                        out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_INTERFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_INTERFACE]
    
    def add_request_characteristic(self):
        self.request_characteristic = HTTPRequestCharacteristic(self.bus, 0, self)
    
    def add_response_characteristic(self):
        self.response_characteristic = HTTPResponseCharacteristic(self.bus, 1, self)
    
    def add_status_characteristic(self):
        self.status_characteristic = StatusCharacteristic(self.bus, 2, self)
    
    def process_http_request(self, request):
        """Process an HTTP request and send the response"""
        parsed = request.parse()
        if not parsed:
            self.send_error_response(request.request_id, 400, "Bad Request")
            return
        
        try:
            # Connect to the local HTTP server
            conn = http.client.HTTPConnection('localhost', self.http_port, timeout=10)
            
            # Prepare headers
            headers = parsed['headers']
            if 'Host' not in headers:
                headers['Host'] = f'localhost:{self.http_port}'
            
            # Send the request
            conn.request(parsed['method'], parsed['path'], parsed['body'], headers)
            
            # Get the response
            response = conn.getresponse()
            
            # Read the response data
            response_data = response.read()
            
            # Build response string
            status_line = f'HTTP/1.1 {response.status} {response.reason}'
            headers_list = [f'{k}: {v}' for k, v in response.headers.items()]
            headers_str = '\r\n'.join(headers_list)
            
            full_response = f'{status_line}\r\n{headers_str}\r\n\r\n'.encode('utf-8') + response_data
            
            # Send the response in chunks
            self.send_response(request.request_id, full_response)
            
            conn.close()
        except Exception as e:
            logger.error(f"Error processing HTTP request: {e}")
            self.send_error_response(request.request_id, 500, f"Internal Server Error: {str(e)}")
    
    def send_error_response(self, request_id, status, message):
        """Send an error response for a request"""
        response = f'HTTP/1.1 {status} {message}\r\nContent-Type: text/plain\r\nContent-Length: {len(message)}\r\n\r\n{message}'.encode('utf-8')
        self.send_response(request_id, response)
    
    def send_response(self, request_id, response_data):
        """Send a response in chunks"""
        # Maximum data size per notification
        max_chunk_size = 512 - 17  # 16 bytes for request ID, 1 byte for flags
        
        # Calculate number of chunks
        total_chunks = (len(response_data) + max_chunk_size - 1) // max_chunk_size
        
        for i in range(total_chunks):
            start = i * max_chunk_size
            end = min(start + max_chunk_size, len(response_data))
            
            # Create flags: bit 0 = first chunk, bit 1 = last chunk
            flags = 0
            if i == 0:
                flags |= 1  # First chunk
            if i == total_chunks - 1:
                flags |= 2  # Last chunk
            
            # Prepare chunk with request ID and flags
            chunk = bytearray(request_id.encode('utf-8')[:16])
            # Pad to 16 bytes if needed
            chunk.extend(b'\0' * (16 - len(chunk)))
            chunk.append(flags)
            chunk.extend(response_data[start:end])
            
            # Send notification
            self.response_characteristic.send_notification(chunk)
            
            # Small delay to avoid overwhelming the client
            time.sleep(0.01)

class HTTPRequestCharacteristic(dbus.service.Object):
    """GATT Characteristic for receiving HTTP requests"""
    def __init__(self, bus, index, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.service = service
        
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_CHARACTERISTIC_INTERFACE: {
                'UUID': BLE_HTTP_REQUEST_CHAR_UUID,
                'Service': self.service.get_path(),
                'Flags': ['write'],
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_INTERFACE,
                        in_signature='s',
                        out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC_INTERFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHARACTERISTIC_INTERFACE]
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        # This characteristic is write-only
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='aya{sv}',
                        out_signature='')
    def WriteValue(self, value, options):
        # Convert dbus.Array to bytes
        received = bytes(value)
        
        if len(received) < 17:  # At least request ID (16 bytes) + flags (1 byte)
            logger.error("Received data too short")
            return
        
        # Extract request ID and flags
        request_id = received[:16].decode('utf-8').rstrip('\0')
        flags = received[16]
        data = received[17:]
        
        is_first = (flags & 1) != 0
        is_last = (flags & 2) != 0
        
        # Get or create request object
        if is_first:
            self.service.pending_requests[request_id] = HTTPRequest(request_id)
        
        request = self.service.pending_requests.get(request_id)
        if not request:
            logger.error(f"Received chunk for unknown request ID: {request_id}")
            return
        
        # Add data to request
        request.add_chunk(data, is_first, is_last)
        
        # If request is complete, process it
        if is_last:
            # Process in a separate thread to avoid blocking
            threading.Thread(
                target=self.service.process_http_request,
                args=(request,)
            ).start()
            
            # Remove from pending requests
            del self.service.pending_requests[request_id]

class HTTPResponseCharacteristic(dbus.service.Object):
    """GATT Characteristic for sending HTTP responses"""
    def __init__(self, bus, index, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.service = service
        self.notifying = False
        
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_CHARACTERISTIC_INTERFACE: {
                'UUID': BLE_HTTP_RESPONSE_CHAR_UUID,
                'Service': self.service.get_path(),
                'Flags': ['notify'],
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_INTERFACE,
                        in_signature='s',
                        out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC_INTERFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHARACTERISTIC_INTERFACE]
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        # This characteristic is notify-only
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='aya{sv}',
                        out_signature='')
    def WriteValue(self, value, options):
        # This characteristic is notify-only
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='',
                        out_signature='')
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        logger.info("HTTP Response notifications enabled")
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='',
                        out_signature='')
    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False
        logger.info("HTTP Response notifications disabled")
    
    def send_notification(self, data):
        if not self.notifying:
            return
        
        self.PropertiesChanged(GATT_CHARACTERISTIC_INTERFACE,
                              {'Value': dbus.Array(data, signature='y')}, [])

    @dbus.service.signal(dbus.PROPERTIES_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

class StatusCharacteristic(dbus.service.Object):
    """GATT Characteristic for service status"""
    def __init__(self, bus, index, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.service = service
        
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_CHARACTERISTIC_INTERFACE: {
                'UUID': BLE_STATUS_CHAR_UUID,
                'Service': self.service.get_path(),
                'Flags': ['read'],
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_INTERFACE,
                        in_signature='s',
                        out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC_INTERFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHARACTERISTIC_INTERFACE]
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        # Return basic status information
        status = {
            'status': 'running',
            'uptime': int(time.time() - start_time),
            'http_port': self.service.http_port,
            'requests_processed': len(self.service.pending_requests)
        }
        
        # Convert to JSON and then to bytes
        import json
        status_json = json.dumps(status)
        return [ord(c) for c in status_json]
    
    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE,
                        in_signature='aya{sv}',
                        out_signature='')
    def WriteValue(self, value, options):
        # This characteristic is read-only
        raise NotSupportedException()

def find_adapter(bus):
    """Find the first available Bluetooth adapter"""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                              DBUS_OM_INTERFACE)
    objects = remote_om.GetManagedObjects()

    for path, interfaces in objects.items():
        if ADAPTER_INTERFACE in interfaces:
            return path
    
    return None

def setup_advertisement(bus, device_name):
    """Set up BLE advertisement"""
    adapter_path = find_adapter(bus)
    if not adapter_path:
        raise Exception("Bluetooth adapter not found")
    
    adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
                           LE_ADVERTISING_MANAGER_INTERFACE)
    
    advertisement = Advertisement(bus, 0, 'peripheral', device_name)
    
    adapter.RegisterAdvertisement(advertisement.get_path(), {},
                                reply_handler=lambda: logger.info("Advertisement registered"),
                                error_handler=lambda error: logger.error(f"Failed to register advertisement: {error}"))
    
    return advertisement

def setup_gatt_server(bus, http_port):
    """Set up BLE GATT server"""
    adapter_path = find_adapter(bus)
    if not adapter_path:
        raise Exception("Bluetooth adapter not found")
    
    adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
                           GATT_MANAGER_INTERFACE)
    
    service = HTTPProxyService(bus, 0, http_port)
    
    adapter.RegisterService(service.get_path(), {},
                          reply_handler=lambda: logger.info("Service registered"),
                          error_handler=lambda error: logger.error(f"Failed to register service: {error}"))
    
    return service

def update_status_file(status):
    """Update the status file with current status"""
    with open(STATUS_FILE, 'w') as f:
        f.write(f"{status}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

def signal_handler(sig, frame):
    """Handle termination signals"""
    logger.info("Stopping BLE HTTP Proxy service...")
    update_status_file("stopped")
    mainloop.quit()
    sys.exit(0)

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='BLE HTTP Proxy for NetTool')
    parser.add_argument('--device-name', default='NetTool',
                      help='Bluetooth device name to advertise (default: NetTool)')
    parser.add_argument('--port', type=int, default=8080,
                      help='HTTP port to proxy (default: 8080)')
    args = parser.parse_args()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Record start time
    start_time = time.time()
    
    # Update status file
    update_status_file("running")
    
    try:
        # Initialize D-Bus
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        
        # Set up BLE advertisement and GATT server
        advertisement = setup_advertisement(bus, args.device_name)
        service = setup_gatt_server(bus, args.port)
        
        # Start main loop
        mainloop = GLib.MainLoop()
        
        logger.info(f"BLE HTTP Proxy service started - Device Name: {args.device_name}, HTTP Port: {args.port}")
        mainloop.run()
    except Exception as e:
        logger.error(f"Error starting BLE HTTP Proxy service: {e}")
        update_status_file("stopped")
        sys.exit(1)
