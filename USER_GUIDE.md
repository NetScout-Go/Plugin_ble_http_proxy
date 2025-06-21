# NetTool BLE HTTP Proxy User Guide

This guide explains how to use the Bluetooth feature of NetTool to access the dashboard from your phone or computer without requiring a WiFi or Ethernet connection.

## What is the BLE HTTP Proxy?

The Bluetooth Low Energy (BLE) HTTP Proxy allows you to access the NetTool dashboard directly through a Bluetooth connection from your phone, tablet, or computer. This is useful in situations where:

- You don't have access to the same WiFi network as the Raspberry Pi
- The Raspberry Pi is not connected to any network
- You're working in a field location without network infrastructure
- You want a secure, direct connection to your NetTool device

## Getting Started

### On the Raspberry Pi

1. Make sure Bluetooth is enabled on your Raspberry Pi:

```bash
sudo systemctl status bluetooth
```

2. From the NetTool dashboard, navigate to the "Bluetooth Dashboard Access" plugin

3. Configure the following settings:
   - Device Name: The name that will appear when scanning for Bluetooth devices
   - HTTP Port: The port the dashboard is running on (usually 8080)
   - Action: Select "Start Bluetooth Service"

4. Click "Run" to start the Bluetooth service

### On Your Mobile Device

1. Make sure Bluetooth is enabled on your mobile device

2. Install a BLE HTTP Proxy client app:
   - For Android: "BLE HTTP Proxy" or similar from Google Play Store
   - For iOS: "BLE Browser" or similar from App Store

3. Open the app and scan for nearby Bluetooth devices

4. Look for the device name you configured (default is "NetTool")

5. Connect to the NetTool device

6. Once connected, you should be able to access the NetTool dashboard in the app's browser

## Features

- **Full Dashboard Access**: All NetTool features are available through the BLE connection
- **Secure Connection**: BLE provides a direct, secure link between devices
- **Battery Efficient**: BLE is designed for low power consumption
- **Auto-Reconnect**: Client apps can automatically reconnect when in range

## Troubleshooting

### Device Not Found

- Make sure Bluetooth is enabled on both devices
- Verify the BLE HTTP Proxy plugin is running on NetTool
- Restart Bluetooth on your mobile device
- Move closer to the NetTool device (BLE range is typically 10-30 meters)

### Slow Performance

- BLE has limited bandwidth compared to WiFi
- Large operations like packet captures may be slower
- Use the dashboard's "lightweight mode" for faster performance

### Connection Drops

- Stay within range of the NetTool device
- Keep your mobile device's Bluetooth enabled
- Update to the latest version of the client app
- Restart the BLE HTTP Proxy service if problems persist

## Technical Specifications

- **BLE Version**: 5.0
- **Max Theoretical Throughput**: ~1.4 Mbps (with optimal conditions)
- **Typical Range**: 10-30 meters (depends on environment)
- **Service UUID**: 00001234-0000-1000-8000-00805f9b34fb

## Security Considerations

- BLE connections are point-to-point and not easily intercepted
- The connection is only active when explicitly started from the dashboard
- Access is limited to devices within Bluetooth range
- Consider stopping the service when not in use for maximum security
