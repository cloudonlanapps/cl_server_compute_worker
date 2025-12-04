#!/bin/bash

################################################################################
#                 CL Server - Start Compute Worker
################################################################################
#
# This script starts a Compute Worker process.
#
# Usage:
#   ./start_worker.sh --worker-id worker-1 --tasks image_resize,image_conversion
#
# Environment Variables (Required):
#   CL_VENV_DIR - Path to directory containing virtual environments
#   CL_SERVER_DIR - Path to data directory
#
# Environment Variables (Optional):
#   WORKER_ID - Unique worker identifier (default: worker-default)
#   WORKER_SUPPORTED_TASKS - Comma-separated task types (default: image_resize,image_conversion)
#
# Worker:
#   - Standalone Compute Worker
#
################################################################################

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR"

# Source common utilities (local to this service)
source "$SCRIPT_DIR/common.sh"

# Worker configuration
WORKER_ID="${WORKER_ID:-worker-default}"
WORKER_SUPPORTED_TASKS="${WORKER_SUPPORTED_TASKS:-image_resize,image_conversion}"
SERVICE_ENV_NAME="compute_worker"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -w|--worker-id)
            WORKER_ID="$2"
            shift 2
            ;;
        -t|--tasks)
            WORKER_SUPPORTED_TASKS="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -w, --worker-id WORKER_ID       Unique worker identifier"
            echo "  -t, --tasks TASK_LIST            Comma-separated task types"
            echo "  -h, --help                       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --worker-id worker_1"
            echo "  $0 -w worker_2 -t image_resize"
            exit 0
            ;;
        *)
            echo -e "${RED}[✗] Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}Starting Compute Worker${NC}"
echo ""

################################################################################
# Validate environment variables
################################################################################

echo "Validating environment variables..."
echo ""

if ! validate_venv_dir; then
    exit 1
fi

echo ""

if ! validate_cl_server_dir; then
    exit 1
fi

echo ""

# Ensure logs directory exists
LOGS_DIR=$(ensure_logs_dir)
if [ $? -ne 0 ]; then
    echo -e "${RED}[✗] Failed to create logs directory${NC}"
    exit 1
fi

echo ""

################################################################################
# Start Compute Worker
################################################################################

print_header "Starting Compute Worker"

if start_worker "$WORKER_ID" "$WORKER_SUPPORTED_TASKS" "$SERVICE_DIR" "$SERVICE_ENV_NAME"; then
    # Worker stopped normally
    echo ""
    echo -e "${YELLOW}[*] Compute worker stopped${NC}"
else
    # Worker failed to start
    echo ""
    echo -e "${RED}[✗] Failed to start Compute worker${NC}"
    exit 1
fi

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
