#!/bin/bash
set -u

SCRIPT_PATH="$(readlink -f "$0")"
PROJECT_DIR="$(dirname "$SCRIPT_PATH")"
PID_FILE="$PROJECT_DIR/.multicam.pid"
LOG_FILE="$PROJECT_DIR/multicam.log"
MULTICAM_BIN="$PROJECT_DIR/.venv/bin/multicam"

cd "$PROJECT_DIR" || exit 1

is_running() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_app() {
    if is_running; then
        echo "Multicam is already running (PID $(cat "$PID_FILE"))."
        return 0
    fi
    rm -f "$PID_FILE"
    nohup "$MULTICAM_BIN" >>"$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" >"$PID_FILE"
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo "Multicam started (PID $pid). Log: $LOG_FILE"
    else
        rm -f "$PID_FILE"
        echo "Multicam failed to start. Check $LOG_FILE" >&2
        return 1
    fi
}

stop_app() {
    if ! is_running; then
        rm -f "$PID_FILE"
        echo "Multicam is not running according to $PID_FILE."
        return 0
    fi
    local pid
    pid="$(cat "$PID_FILE")"
    kill "$pid"
    for _ in $(seq 1 50); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "Multicam stopped."
            return 0
        fi
        sleep 0.1
    done
    echo "Multicam PID $pid did not stop within 5 seconds." >&2
    return 1
}

case "${1:-run}" in
    start) start_app ;;
    stop) stop_app ;;
    restart) stop_app && start_app ;;
    status)
        if is_running; then
            echo "Multicam is running (PID $(cat "$PID_FILE"))."
        else
            echo "Multicam is stopped."
            exit 1
        fi
        ;;
    logs)
        touch "$LOG_FILE"
        tail -n 100 -f "$LOG_FILE"
        ;;
    run) exec "$MULTICAM_BIN" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|run}" >&2
        exit 2
        ;;
esac
