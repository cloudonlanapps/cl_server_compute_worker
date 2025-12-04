#!/bin/bash

################################################################################
#            Standalone Compute Worker - Start Script
################################################################################
#
# This script starts a standalone Compute Worker.
#
# Usage:
#   ./start_worker.sh --worker-id worker-1 --tasks image_resize,image_conversion
#
# Environment Variables (Required):
#   CL_SERVER_DIR - Path to data directory
#
# Environment Variables (Optional):
#   WORKER_ID - Unique worker identifier (default: worker-default)
#   WORKER_SUPPORTED_TASKS - Comma-separated task types (default: image_resize,image_conversion)
#   WORKER_POLL_INTERVAL - Queue poll interval in seconds (default: 5)
#
################################################################################

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
WORKER_ID="${WORKER_ID:-worker-default}"
WORKER_SUPPORTED_TASKS="${WORKER_SUPPORTED_TASKS:-image_resize,image_conversion}"

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

echo -e "${BLUE}Starting Standalone Compute Worker${NC}"
echo "Worker ID: $WORKER_ID"
echo "Supported Tasks: $WORKER_SUPPORTED_TASKS"
echo ""

# Validate CL_SERVER_DIR
if [ -z "$CL_SERVER_DIR" ]; then
    echo -e "${RED}[✗] Error: CL_SERVER_DIR environment variable must be set${NC}"
    echo -e "${YELLOW}    Example: export CL_SERVER_DIR=/path/to/data${NC}"
    exit 1
fi

if [ ! -w "$CL_SERVER_DIR" ]; then
    echo -e "${RED}[✗] Error: No write permission for CL_SERVER_DIR: $CL_SERVER_DIR${NC}"
    exit 1
fi

echo -e "${GREEN}[✓] CL_SERVER_DIR is set: $CL_SERVER_DIR${NC}"
echo ""

# Run worker
echo -e "${BLUE}[*] Starting worker...${NC}"
export WORKER_ID="$WORKER_ID"
export WORKER_SUPPORTED_TASKS="$WORKER_SUPPORTED_TASKS"

cd "$SCRIPT_DIR"
python -m src.worker --worker-id "$WORKER_ID" --tasks "$WORKER_SUPPORTED_TASKS"
