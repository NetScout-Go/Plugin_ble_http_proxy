#!/bin/bash
# Install dependencies for the BLE HTTP Proxy plugin

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}NetTool BLE HTTP Proxy - Dependency Installer${NC}"
echo "This script will install the required dependencies for the BLE HTTP Proxy plugin."
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${YELLOW}This script should be run as root.${NC}"
  echo "Please run with sudo:"
  echo "  sudo $0"
  exit 1
fi

echo -e "${BLUE}Checking system...${NC}"

# Check if we're on a Raspberry Pi
if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
  PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
  echo -e "${GREEN}Detected: $PI_MODEL${NC}"
else
  echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi.${NC}"
  echo "The BLE HTTP Proxy is primarily designed for Raspberry Pi."
  echo "It may still work on other Linux systems with BlueZ, but is not guaranteed."
  echo
  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Installation cancelled.${NC}"
    exit 1
  fi
fi

echo -e "${BLUE}Installing package dependencies...${NC}"
apt-get update
apt-get install -y python3 python3-pip bluez bluez-tools bluetooth python3-dbus python3-gi

echo -e "${BLUE}Checking Bluetooth service...${NC}"
systemctl enable bluetooth
systemctl start bluetooth

# Check if the Bluetooth service is running
if systemctl is-active --quiet bluetooth; then
  echo -e "${GREEN}Bluetooth service is running.${NC}"
else
  echo -e "${RED}Bluetooth service is not running. Trying to start...${NC}"
  systemctl start bluetooth
  
  if systemctl is-active --quiet bluetooth; then
    echo -e "${GREEN}Bluetooth service started successfully.${NC}"
  else
    echo -e "${RED}Failed to start Bluetooth service. Please check your system.${NC}"
    exit 1
  fi
fi

echo -e "${BLUE}Installing Python dependencies...${NC}"
pip3 install bluepy

# Set capabilities for bluepy-helper to allow non-root BLE scanning
echo -e "${BLUE}Setting capabilities for bluepy-helper...${NC}"
BLUEPY_HELPER=$(find /usr -name bluepy-helper 2>/dev/null | head -n 1)
if [ -n "$BLUEPY_HELPER" ]; then
  setcap 'cap_net_raw,cap_net_admin+eip' "$BLUEPY_HELPER"
  echo -e "${GREEN}Set capabilities for $BLUEPY_HELPER${NC}"
else
  echo -e "${YELLOW}Warning: Could not find bluepy-helper. BLE scanning may require root privileges.${NC}"
fi

# Set capabilities for Python to allow non-root BLE scanning
echo -e "${BLUE}Setting capabilities for Python...${NC}"
PYTHON_PATH=$(which python3)
setcap 'cap_net_raw,cap_net_admin+eip' "$PYTHON_PATH"
echo -e "${GREEN}Set capabilities for $PYTHON_PATH${NC}"

echo
echo -e "${GREEN}Installation complete!${NC}"
echo "You can now use the BLE HTTP Proxy plugin from the NetTool dashboard."
echo
echo -e "${YELLOW}Note:${NC} You may need to reboot your Raspberry Pi for all changes to take effect."
echo "To reboot, run: sudo reboot"
