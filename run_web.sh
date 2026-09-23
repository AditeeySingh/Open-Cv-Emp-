#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PYTHON_BIN="python3"
if [ -f "/opt/anaconda3/bin/python3" ]; then
    PYTHON_BIN="/opt/anaconda3/bin/python3"
fi

OCCUPIED_PID=$(lsof -ti :5000 2>/dev/null)
if [ -n "$OCCUPIED_PID" ]; then
    echo "Clearing previous process on port 5000 (PID: $OCCUPIED_PID)..."
    kill -9 $OCCUPIED_PID 2>/dev/null || true
    sleep 0.5
fi

$PYTHON_BIN "$DIR/app.py" "$@"
