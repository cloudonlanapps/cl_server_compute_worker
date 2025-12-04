#!/bin/bash

################################################################################
#                     CL Server - Common Utilities
################################################################################
#
# This script contains shared functions used by service start scripts.
#
################################################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

################################################################################
# Function to validate CL_VENV_DIR environment variable
################################################################################
validate_venv_dir() {
    if [ -z "$CL_VENV_DIR" ]; then
        echo -e "${RED}[✗] Error: CL_VENV_DIR environment variable must be set${NC}"
        echo -e "${YELLOW}    Example: export CL_VENV_DIR=/path/to/venv${NC}"
        return 1
    fi

    if [ ! -w "$(dirname "$CL_VENV_DIR")" ]; then
        echo -e "${RED}[✗] Error: No write permission for parent of CL_VENV_DIR: $CL_VENV_DIR${NC}"
        return 1
    fi

    echo -e "${GREEN}[✓] CL_VENV_DIR is set and writable: $CL_VENV_DIR${NC}"
    return 0
}

################################################################################
# Function to check if port is in use
################################################################################
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

################################################################################
# Function to validate CL_SERVER_DIR environment variable
################################################################################
validate_cl_server_dir() {
    if [ -z "$CL_SERVER_DIR" ]; then
        echo -e "${RED}[✗] Error: CL_SERVER_DIR environment variable must be set${NC}"
        echo -e "${YELLOW}    Example: export CL_SERVER_DIR=/path/to/data${NC}"
        return 1
    fi

    if [ ! -w "$CL_SERVER_DIR" ]; then
        echo -e "${RED}[✗] Error: No write permission for CL_SERVER_DIR: $CL_SERVER_DIR${NC}"
        echo -e "${YELLOW}    Please ensure the directory exists and you have write permissions${NC}"
        return 1
    fi

    echo -e "${GREEN}[✓] CL_SERVER_DIR is set and writable: $CL_SERVER_DIR${NC}"
    return 0
}

################################################################################
# Function to ensure logs directory exists
################################################################################
ensure_logs_dir() {
    local logs_dir="$CL_SERVER_DIR/run_logs"

    if [ ! -d "$logs_dir" ]; then
        if ! mkdir -p "$logs_dir" 2>/dev/null; then
            echo -e "${RED}[✗] Error: Failed to create logs directory: $logs_dir${NC}"
            return 1
        fi
    fi

    echo "$logs_dir"
    return 0
}

################################################################################
# Function to setup Python virtual environment
################################################################################
setup_venv() {
    local service_path=$1
    local service_name=$2

    # CL_VENV_DIR is required - must be set by caller
    if [ -z "$CL_VENV_DIR" ]; then
        echo -e "${RED}[✗] Error: CL_VENV_DIR environment variable must be set${NC}"
        echo -e "${YELLOW}    Example: export CL_VENV_DIR=/path/to/venv${NC}"
        return 1
    fi

    local venv_path="$CL_VENV_DIR/${service_name}_env"

    if [ ! -d "$venv_path" ]; then
        echo -e "${YELLOW}[!] Virtual environment not found. Creating at: $venv_path${NC}"
        python -m venv "$venv_path"
        source "$venv_path/bin/activate"
        pip install -q -e "$service_path" 2>/dev/null || true
    else
        source "$venv_path/bin/activate"
    fi
}

################################################################################
# Function to start a worker (foreground - for direct execution)
################################################################################
start_worker() {
    local worker_id=$1
    local supported_tasks=$2
    local service_path=$3
    local service_env_name=$4

    echo -e "${BLUE}[*] Starting Compute Worker...${NC}"

    # Setup venv
    setup_venv "$service_path" "$service_env_name"

    echo -e "${GREEN}[✓] Compute Worker starting${NC}"
    echo -e "${BLUE}[*] Worker ID: $worker_id${NC}"
    echo -e "${BLUE}[*] Supported Tasks: $supported_tasks${NC}"
    echo -e "${BLUE}[*] Press Ctrl+C to stop the worker${NC}"
    echo ""

    # Start the worker in FOREGROUND (direct execution)
    # Output to stdout/stderr - parent process handles logging
    WORKER_ID="$worker_id" WORKER_SUPPORTED_TASKS="$supported_tasks" CL_SERVER_DIR="$CL_SERVER_DIR" python -m src.worker

    # This line is only reached if the worker stops
    return 0
}

################################################################################
# Function to print header
################################################################################
print_header() {
    local title=$1
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}                    ${title}${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

################################################################################
# Function to print section
################################################################################
print_section() {
    local title=$1
    echo -e "${BLUE}[*] ${title}${NC}"
}

################################################################################
# Export functions so they can be used in sourced scripts
################################################################################
export -f validate_venv_dir
export -f check_port
export -f validate_cl_server_dir
export -f ensure_logs_dir
export -f setup_venv
export -f start_worker
export -f print_header
export -f print_section
