#!/bin/bash
# monitor_ble_proxy.sh
# A simple monitoring tool for the BLE HTTP Proxy service

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to check service status
check_service_status() {
    if pgrep -f "pi_zero_ble_service.py" > /dev/null; then
        SERVICE_PID=$(pgrep -f "pi_zero_ble_service.py")
        echo -e "${GREEN}BLE HTTP Proxy service is running (PID: $SERVICE_PID)${NC}"
        return 0
    else
        echo -e "${RED}BLE HTTP Proxy service is NOT running${NC}"
        return 1
    fi
}

# Function to check BlueZ status
check_bluez_status() {
    if systemctl is-active --quiet bluetooth; then
        echo -e "${GREEN}Bluetooth service is running${NC}"
        return 0
    else
        echo -e "${RED}Bluetooth service is NOT running${NC}"
        return 1
    fi
}

# Function to check BLE advertisement status
check_advertisement_status() {
    # This requires sudo, so we'll check if we're running as root
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}Cannot check BLE advertisement status without root privileges${NC}"
        return 2
    fi
    
    # Use hcitool to scan for the BLE advertisement
    echo -e "${BLUE}Scanning for BLE advertisements (3 seconds)...${NC}"
    DEVICE_NAME=${1:-"NetTool"}
    
    # Use a timeout to limit the scan time
    SCAN_OUTPUT=$(timeout 3 hcitool lescan 2>/dev/null | grep "$DEVICE_NAME" || true)
    
    if [ -n "$SCAN_OUTPUT" ]; then
        echo -e "${GREEN}BLE advertisement found: $SCAN_OUTPUT${NC}"
        return 0
    else
        echo -e "${RED}No BLE advertisement found for '$DEVICE_NAME'${NC}"
        return 1
    fi
}

# Function to check connection metrics
check_connection_metrics() {
    if check_service_status >/dev/null; then
        SERVICE_PID=$(pgrep -f "pi_zero_ble_service.py")
        # Try to get service logs from journalctl
        echo -e "${BLUE}Recent connection metrics:${NC}"
        
        # Check for log lines containing "connected" or "disconnected"
        # This assumes the Python script logs to syslog/journal
        CONNECTION_LOGS=$(journalctl -p info --since "5 minutes ago" _PID=$SERVICE_PID 2>/dev/null | grep -E "connected|disconnected|request|response" | tail -10 || true)
        
        if [ -n "$CONNECTION_LOGS" ]; then
            echo "$CONNECTION_LOGS"
        else
            echo "No recent connection logs found"
        fi
    fi
}

# Function to display a menu
show_menu() {
    echo -e "${BLUE}BLE HTTP Proxy Monitor${NC}"
    echo "1. Check service status"
    echo "2. Check Bluetooth status"
    echo "3. Check BLE advertisement"
    echo "4. View connection metrics"
    echo "5. Start BLE service"
    echo "6. Stop BLE service"
    echo "7. Restart BLE service"
    echo "8. Continuous monitoring (CTRL+C to exit)"
    echo "9. Exit"
    echo -n "Select an option: "
}

# Function to start the BLE service
start_service() {
    if check_service_status >/dev/null; then
        echo -e "${YELLOW}Service is already running${NC}"
        return
    fi
    
    echo -e "${BLUE}Starting BLE HTTP Proxy service...${NC}"
    cd "$SCRIPT_DIR"
    
    # Get configuration from arguments or use defaults
    DEVICE_NAME=${1:-"NetTool"}
    PORT=${2:-8080}
    
    # Start the service
    python3 pi_zero_ble_service.py --device "$DEVICE_NAME" --port "$PORT" &
    sleep 2
    
    if check_service_status >/dev/null; then
        echo -e "${GREEN}Service started successfully${NC}"
    else
        echo -e "${RED}Failed to start service${NC}"
    fi
}

# Function to stop the BLE service
stop_service() {
    if ! check_service_status >/dev/null; then
        echo -e "${YELLOW}Service is not running${NC}"
        return
    fi
    
    echo -e "${BLUE}Stopping BLE HTTP Proxy service...${NC}"
    pkill -f "pi_zero_ble_service.py" || true
    sleep 2
    
    if ! check_service_status >/dev/null; then
        echo -e "${GREEN}Service stopped successfully${NC}"
    else
        echo -e "${RED}Failed to stop service${NC}"
    fi
}

# Function for continuous monitoring
continuous_monitoring() {
    echo -e "${BLUE}Starting continuous monitoring (CTRL+C to exit)...${NC}"
    
    while true; do
        clear
        echo -e "${BLUE}=== BLE HTTP Proxy Status ($(date)) ===${NC}"
        echo ""
        check_service_status
        check_bluez_status
        
        if [ "$EUID" -eq 0 ]; then
            echo ""
            check_advertisement_status "$1"
        fi
        
        echo ""
        check_connection_metrics
        
        echo ""
        echo -e "${YELLOW}Press CTRL+C to exit${NC}"
        sleep 5
    done
}

# Main script execution
if [ "$1" == "--monitor" ]; then
    continuous_monitoring "$2"
    exit 0
fi

if [ "$1" == "--start" ]; then
    start_service "$2" "$3"
    exit 0
fi

if [ "$1" == "--stop" ]; then
    stop_service
    exit 0
fi

if [ "$1" == "--restart" ]; then
    stop_service
    sleep 1
    start_service "$2" "$3"
    exit 0
fi

if [ "$1" == "--status" ]; then
    check_service_status
    check_bluez_status
    
    if [ "$EUID" -eq 0 ]; then
        check_advertisement_status "$2"
    fi
    
    exit 0
fi

# If no arguments, show the interactive menu
while true; do
    clear
    show_menu
    read -r option
    
    case $option in
        1) check_service_status; read -p "Press Enter to continue..." ;;
        2) check_bluez_status; read -p "Press Enter to continue..." ;;
        3) check_advertisement_status; read -p "Press Enter to continue..." ;;
        4) check_connection_metrics; read -p "Press Enter to continue..." ;;
        5) 
            read -p "Device name [NetTool]: " device_name
            device_name=${device_name:-"NetTool"}
            read -p "HTTP port [8080]: " port
            port=${port:-8080}
            start_service "$device_name" "$port"
            read -p "Press Enter to continue..."
            ;;
        6) stop_service; read -p "Press Enter to continue..." ;;
        7)
            read -p "Device name [NetTool]: " device_name
            device_name=${device_name:-"NetTool"}
            read -p "HTTP port [8080]: " port
            port=${port:-8080}
            stop_service
            sleep 1
            start_service "$device_name" "$port"
            read -p "Press Enter to continue..."
            ;;
        8)
            read -p "Device name [NetTool]: " device_name
            device_name=${device_name:-"NetTool"}
            continuous_monitoring "$device_name"
            ;;
        9) exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}"; sleep 1 ;;
    esac
done
