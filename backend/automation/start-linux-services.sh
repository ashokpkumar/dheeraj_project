#!/bin/bash
# start-linux-services.sh
# Start Celery worker and beat scheduler for Linux/Docker deployment
#
# Usage:
#   ./start-linux-services.sh              # Start both worker and beat
#   ./start-linux-services.sh --worker     # Start only worker
#   ./start-linux-services.sh --beat       # Start only beat
#   ./start-linux-services.sh --api        # Start only API server
#
# Environment variables (set in .env):
#   WINDOWS_SERVICE_HOST   - IP/hostname of Windows service
#   WINDOWS_SERVICE_PORT   - Port of Windows service (default: 5555)
#   CELERY_BROKER_URL      - Redis broker URL
#   DB_HOST, DB_PORT, etc. - Database configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${CYAN}╔═════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   Linux Services Startup                               ║${NC}"
    echo -e "${CYAN}╚═════════════════════════════════════════════════════════╝${NC}"
}

print_section() {
    echo -e "${CYAN}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if .env file exists
check_env() {
    if [ ! -f ".env" ]; then
        print_error ".env file not found"
        echo "Please create .env file with required variables:"
        echo "  WINDOWS_SERVICE_HOST=<windows-ip>"
        echo "  WINDOWS_SERVICE_PORT=5555"
        echo "  CELERY_BROKER_URL=redis://localhost:6379/0"
        echo "  CELERY_RESULT_BACKEND=redis://localhost:6379/0"
        exit 1
    fi
    print_success ".env file found"
}

# Check dependencies
check_dependencies() {
    print_section "Checking dependencies"
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found"
        exit 1
    fi
    print_success "Python 3 found"
    
    if ! python3 -c "import django" 2>/dev/null; then
        print_error "Django not installed"
        exit 1
    fi
    print_success "Django installed"
    
    if ! python3 -c "import celery" 2>/dev/null; then
        print_error "Celery not installed"
        exit 1
    fi
    print_success "Celery installed"
}

# Run database migrations
run_migrations() {
    print_section "Running database migrations"
    python3 manage.py migrate --noinput
    print_success "Migrations completed"
}

# Start Celery Worker
start_worker() {
    print_section "Starting Celery Worker"
    echo "This will remain in foreground. Press Ctrl+C to stop."
    echo ""
    celery -A automation worker --loglevel=info
}

# Start Celery Beat
start_beat() {
    print_section "Starting Celery Beat Scheduler"
    echo "⚠️  Only run ONE instance in production!"
    echo "Press Ctrl+C to stop."
    echo ""
    celery -A automation beat --loglevel=info
}

# Start both in background (requires GNU screen or tmux)
start_both() {
    print_section "Starting Celery Worker and Beat in background"
    
    # Check for tmux
    if command -v tmux &> /dev/null; then
        print_success "Using tmux for background processes"
        
        # Create new session
        tmux new-session -d -s celery
        
        # Start worker in first window
        tmux new-window -t celery -n worker
        tmux send-keys -t celery:worker "celery -A automation worker --loglevel=info" Enter
        
        # Start beat in second window
        tmux new-window -t celery -n beat
        tmux send-keys -t celery:beat "celery -A automation beat --loglevel=info" Enter
        
        echo "Services started in tmux session 'celery'"
        echo "View logs: tmux attach -t celery"
        echo "View worker: tmux select-window -t celery:worker"
        echo "View beat: tmux select-window -t celery:beat"
        return 0
    fi
    
    # Fallback: screen
    if command -v screen &> /dev/null; then
        print_success "Using screen for background processes"
        
        # Start worker in background
        screen -d -m -S celery-worker celery -A automation worker --loglevel=info
        # Start beat in background
        screen -d -m -S celery-beat celery -A automation beat --loglevel=info
        
        echo "Services started in background"
        echo "View worker logs: screen -r celery-worker"
        echo "View beat logs: screen -r celery-beat"
        return 0
    fi
    
    print_error "tmux or screen not installed. Please install one:"
    echo "  Ubuntu/Debian: sudo apt-get install tmux"
    echo "  Or run services separately in different terminals"
    exit 1
}

# Start Django API server
start_api() {
    print_section "Starting Django API Server"
    echo "Server will be available at http://localhost:8000"
    echo "Press Ctrl+C to stop."
    echo ""
    python3 manage.py runserver 0.0.0.0:8000
}

# Test Windows service connectivity
test_windows_service() {
    print_section "Testing Windows Service connectivity"
    
    source .env
    WINDOWS_HOST="${WINDOWS_SERVICE_HOST:-localhost}"
    WINDOWS_PORT="${WINDOWS_SERVICE_PORT:-5555}"
    
    echo "Connecting to: http://$WINDOWS_HOST:$WINDOWS_PORT/health"
    
    if curl -s "http://$WINDOWS_HOST:$WINDOWS_PORT/health" > /dev/null 2>&1; then
        print_success "Windows service is reachable"
    else
        print_warning "Cannot reach Windows service at http://$WINDOWS_HOST:$WINDOWS_PORT"
        echo "Make sure:"
        echo "  1. windows_automation_service.py is running on Windows"
        echo "  2. WINDOWS_SERVICE_HOST is set correctly in .env"
        echo "  3. Windows firewall allows traffic on port $WINDOWS_PORT"
    fi
}

# Main
print_header

MODE="${1:-all}"

case "$MODE" in
    --worker)
        check_env
        check_dependencies
        run_migrations
        test_windows_service
        start_worker
        ;;
    --beat)
        check_env
        check_dependencies
        test_windows_service
        start_beat
        ;;
    --api)
        check_env
        check_dependencies
        run_migrations
        start_api
        ;;
    --both)
        check_env
        check_dependencies
        run_migrations
        test_windows_service
        start_both
        ;;
    all|*)
        check_env
        check_dependencies
        run_migrations
        test_windows_service
        
        echo ""
        echo "Choose what to start:"
        echo "  1) Worker only"
        echo "  2) Beat scheduler only"
        echo "  3) Both (in background)"
        echo "  4) API server"
        echo "  5) All services"
        
        read -p "Enter choice (1-5): " choice
        
        case $choice in
            1) start_worker ;;
            2) start_beat ;;
            3) start_both ;;
            4) start_api ;;
            5) 
                start_both
                sleep 2
                start_api
                ;;
            *) echo "Invalid choice"; exit 1 ;;
        esac
        ;;
esac
