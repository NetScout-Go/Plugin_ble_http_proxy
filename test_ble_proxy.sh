#!/bin/bash
# test_ble_proxy.sh
# Automated test script for the BLE HTTP Proxy plugin

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting BLE HTTP Proxy test script${NC}"
echo "This script will test the BLE HTTP Proxy plugin functionality"

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (sudo)${NC}"
  exit 1
fi

# Check if BlueZ is installed
echo -e "${YELLOW}Checking BlueZ installation...${NC}"
if ! command -v bluetoothctl &> /dev/null; then
    echo -e "${RED}Error: bluetoothctl not found. Please install BlueZ.${NC}"
    exit 1
fi
echo -e "${GREEN}BlueZ is installed.${NC}"

# Check if Bluetooth service is running
echo -e "${YELLOW}Checking Bluetooth service...${NC}"
if ! systemctl is-active --quiet bluetooth; then
    echo -e "${RED}Error: Bluetooth service is not running.${NC}"
    echo "Attempting to start the service..."
    systemctl start bluetooth
    sleep 2
    if ! systemctl is-active --quiet bluetooth; then
        echo -e "${RED}Failed to start Bluetooth service.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}Bluetooth service is running.${NC}"

# Check for Python dependencies
echo -e "${YELLOW}Checking Python dependencies...${NC}"
PYTHON_DEPS=("dbus-python" "pygobject" "bluepy")
MISSING_DEPS=()

for dep in "${PYTHON_DEPS[@]}"; do
    if ! python3 -c "import $dep" 2>/dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo -e "${RED}Missing Python dependencies: ${MISSING_DEPS[*]}${NC}"
    echo "You can install them using the install_dependencies.sh script."
    exit 1
fi
echo -e "${GREEN}All required Python dependencies are installed.${NC}"

# Get the NetTool directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETTOOL_DIR="$(cd "$SCRIPT_DIR/../../../../" && pwd)"

# Check if NetTool is running
echo -e "${YELLOW}Checking if NetTool is running...${NC}"
if ! pgrep -f "main.go" > /dev/null; then
    echo -e "${YELLOW}NetTool doesn't seem to be running. Starting it in background...${NC}"
    cd "$NETTOOL_DIR"
    go run main.go &
    NETTOOL_PID=$!
    # Give NetTool time to start
    sleep 5
    echo -e "${GREEN}NetTool started with PID $NETTOOL_PID${NC}"
else
    echo -e "${GREEN}NetTool is already running.${NC}"
fi

# Get Bluetooth adapter name
BT_ADAPTER=$(hciconfig | grep -o "hci[0-9]" | head -1)
if [ -z "$BT_ADAPTER" ]; then
    echo -e "${RED}No Bluetooth adapter found.${NC}"
    exit 1
fi
echo -e "${GREEN}Using Bluetooth adapter: $BT_ADAPTER${NC}"

# Make sure the BLE service isn't already running
echo -e "${YELLOW}Making sure the BLE service isn't already running...${NC}"
if pgrep -f "pi_zero_ble_service.py" > /dev/null; then
    echo -e "${YELLOW}BLE service is already running. Stopping it...${NC}"
    pkill -f "pi_zero_ble_service.py"
    sleep 2
fi

# Start the BLE HTTP Proxy service
echo -e "${YELLOW}Starting the BLE HTTP Proxy service...${NC}"
cd "$SCRIPT_DIR"
python3 pi_zero_ble_service.py --device "NetTool-Test" --port 8080 &
BLE_SERVICE_PID=$!
sleep 5

# Check if the service started successfully
if ! pgrep -f "pi_zero_ble_service.py" > /dev/null; then
    echo -e "${RED}Failed to start the BLE service.${NC}"
    exit 1
fi
echo -e "${GREEN}BLE HTTP Proxy service started with PID $BLE_SERVICE_PID${NC}"

# Test the BLE service using the Python client
echo -e "${YELLOW}Testing BLE service with Python client...${NC}"
echo "Scanning for BLE devices..."
SCAN_OUTPUT=$(python3 client/test_ble_client.py --scan --timeout 5)
echo "$SCAN_OUTPUT"

if ! echo "$SCAN_OUTPUT" | grep -q "NetTool-Test"; then
    echo -e "${RED}BLE device 'NetTool-Test' not found in scan results.${NC}"
    echo "Stopping the BLE service..."
    kill $BLE_SERVICE_PID 2>/dev/null || true
    if [ -n "$NETTOOL_PID" ]; then
        kill $NETTOOL_PID 2>/dev/null || true
    fi
    exit 1
fi

echo -e "${GREEN}BLE device 'NetTool-Test' found in scan results.${NC}"
echo -e "${YELLOW}Sending a test HTTP request...${NC}"

# Get the MAC address of the device
MAC_ADDRESS=$(echo "$SCAN_OUTPUT" | grep "NetTool-Test" | awk '{print $1}')
echo "Connecting to device with MAC: $MAC_ADDRESS"

# Send a simple GET request to the dashboard
HTTP_RESPONSE=$(python3 client/test_ble_client.py --connect "$MAC_ADDRESS" --request "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")

# Check if we got a valid HTTP response
if echo "$HTTP_RESPONSE" | grep -q "HTTP/1.1"; then
    echo -e "${GREEN}Successfully received HTTP response via BLE!${NC}"
    echo "First 100 characters of the response:"
    echo "$HTTP_RESPONSE" | head -c 100
    echo "..."
else
    echo -e "${RED}Failed to get a valid HTTP response.${NC}"
    echo "Response received:"
    echo "$HTTP_RESPONSE"
fi

# Stop the BLE service
echo -e "${YELLOW}Stopping the BLE HTTP Proxy service...${NC}"
kill $BLE_SERVICE_PID 2>/dev/null || true
sleep 2

# Check if we need to stop NetTool
if [ -n "$NETTOOL_PID" ]; then
    echo -e "${YELLOW}Stopping NetTool...${NC}"
    kill $NETTOOL_PID 2>/dev/null || true
fi

echo -e "${GREEN}Test completed.${NC}"
