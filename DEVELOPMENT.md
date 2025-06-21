# BLE HTTP Proxy Plugin Development Guide

This document provides technical details for developers who want to understand, modify, or extend the BLE HTTP Proxy plugin for NetTool.

## Architecture Overview

The BLE HTTP Proxy plugin implements a Bluetooth Low Energy (BLE) GATT server that acts as a proxy for HTTP requests. The high-level architecture is as follows:

1. The Go plugin (`plugin.go`) manages the lifecycle of the BLE service
2. A Python script (`pi_zero_ble_service.py`) implements the actual BLE GATT server
3. The BLE service exposes characteristics for sending HTTP requests and receiving responses
4. Client applications connect to the BLE service and use it to access the NetTool dashboard

## Go Plugin

The Go plugin (`plugin.go`) provides the following functionality:

- Integration with the NetTool plugin system
- Parameter validation and processing
- Starting and stopping the Python BLE service
- Status monitoring and management

### Key Functions

- `executePlugin`: Entry point for the plugin, processes parameters and calls appropriate actions
- `startBLEProxy`: Starts the Python BLE service
- `stopBLEProxy`: Stops the running BLE service
- `getBLEProxyStatus`: Checks the current status of the BLE service

## Python BLE Service

The Python script (`pi_zero_ble_service.py`) implements the BLE GATT server using the BlueZ D-Bus API. It provides the following functionality:

- BLE GATT server with custom service and characteristics
- BLE advertisement to make the service discoverable
- HTTP request processing
- Chunked data transfer for large requests/responses

### Key Classes

- `Advertisement`: Implements the BLE advertisement
- `HTTPProxyService`: Implements the GATT service
- `HTTPRequestCharacteristic`: Handles incoming HTTP requests
- `HTTPResponseCharacteristic`: Sends HTTP responses
- `StatusCharacteristic`: Provides service status information

## BLE Protocol

The BLE HTTP Proxy uses a custom protocol for transferring HTTP requests and responses:

### Service and Characteristic UUIDs

- Service UUID: `00001234-0000-1000-8000-00805f9b34fb`
- HTTP Request Characteristic UUID: `00001235-0000-1000-8000-00805f9b34fb`
- HTTP Response Characteristic UUID: `00001236-0000-1000-8000-00805f9b34fb`
- Status Characteristic UUID: `00001237-0000-1000-8000-00805f9b34fb`

### Request Format

Each request chunk has the following format:

```text
+----------------+-------+------------------+
| Request ID     | Flags | Request Data     |
| (16 bytes)     | (1B)  | (variable)       |
+----------------+-------+------------------+
```

The flags byte uses the following bits:

- Bit 0: Set if this is the first chunk
- Bit 1: Set if this is the last chunk

### Response Format

Responses use the same format as requests:

```text
+----------------+-------+------------------+
| Request ID     | Flags | Response Data    |
| (16 bytes)     | (1B)  | (variable)       |
+----------------+-------+------------------+
```

## Client Implementation

The plugin includes two client implementations:

1. Python client (`test_ble_client.py`): For testing and debugging
2. JavaScript client (`nettool-ble-client.js`): For web browser integration

### Python Client

The Python client uses the `bluepy` library to connect to the BLE service. It provides command-line options for scanning, connecting, and sending HTTP requests.

### JavaScript Client

The JavaScript client uses the Web Bluetooth API to connect to the BLE service. It provides a Promise-based API similar to the Fetch API for sending HTTP requests.

## Extending the Plugin

### Adding New Characteristics

To add a new characteristic to the BLE service:

1. Define a new UUID in both `plugin.go` and `pi_zero_ble_service.py`
2. Create a new characteristic class in `pi_zero_ble_service.py`
3. Add the characteristic to the `HTTPProxyService` class
4. Update the client implementations to use the new characteristic

### Supporting New Data Types

To support new data types:

1. Modify the `HTTPRequestCharacteristic` class to handle the new data type
2. Update the client implementations to send the new data type
3. Add appropriate parsing and conversion in both server and client

### Improving Security

The current implementation focuses on functionality rather than security. To improve security:

1. Add authentication to the BLE connection
2. Implement encryption for the data
3. Add access control mechanisms
4. Implement request validation

## Troubleshooting Development Issues

### BlueZ D-Bus API

The BlueZ D-Bus API can be challenging to work with. Common issues include:

- Permission problems: Make sure the Python script has the necessary capabilities
- D-Bus configuration: Check that the BlueZ service is properly registered with D-Bus
- API changes: The BlueZ API can change between versions

To debug D-Bus issues, use the following commands:

```bash
# Check D-Bus services
dbus-send --system --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames

# Check BlueZ objects
dbus-send --system --dest=org.bluez --type=method_call --print-reply /org/bluez org.freedesktop.DBus.ObjectManager.GetManagedObjects
```

### BLE Connection Issues

BLE connections can be affected by various factors:

- Range: Make sure the devices are within range
- Interference: Other wireless devices can interfere with BLE
- Power: Low power on either device can affect connection quality

To debug BLE connection issues:

```bash
# Check Bluetooth adapter status
hciconfig

# Scan for BLE devices
sudo hcitool lescan

# Check BLE advertisements
sudo btmon
```

## Performance Considerations

BLE has limited bandwidth compared to Wi-Fi or Ethernet. To optimize performance:

1. Minimize the size of HTTP requests and responses
2. Use appropriate MTU sizes
3. Implement caching where possible
4. Consider compression for large responses
5. Use chunked transfer for large data
