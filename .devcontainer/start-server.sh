#!/usr/bin/env bash
# Starts the study server in the background whenever the codespace starts (unless it is already running).
# Its output goes to server/data/server.log; show the links any time with:  python3 server/server.py --links
cd "$(dirname "$0")/.." || exit 1
mkdir -p server/data
if python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', 8000)) == 0 else 1)"; then
  echo "Pizza study server is already running."
else
  nohup python3 server/server.py >> server/data/server.log 2>&1 &
  echo "Pizza study server started."
fi
