#!/bin/bash
# Kill any process on port 8000 and start the dev server

PORT=8000

PID=$(lsof -ti:$PORT)
if [ -n "$PID" ]; then
  echo "Killing existing process on port $PORT (PID $PID)..."
  kill $PID
  sleep 1
fi

echo "Starting AgentShield dev server on port $PORT..."
uvicorn backend.main:app --reload --port $PORT
