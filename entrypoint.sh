#!/bin/bash
set -uo pipefail

ACC_INSTALL_DIR="${ACC_INSTALL_DIR:-/data/accserver}"

mkdir -p /data/cfg /data/results /data/logs "$ACC_INSTALL_DIR"

server_present() {
  find "$ACC_INSTALL_DIR" -iname accServer.exe 2>/dev/null | grep -q .
}

python3 -c "import sys; sys.path.insert(0, '/app'); import acc_config; acc_config.ensure_defaults()"

if ! server_present; then
  echo "ERROR: no ACC server found in ${ACC_INSTALL_DIR}." >&2
  echo "Mount pre-downloaded server files via ACC_SERVER_PATH (see README's" >&2
  echo "'Providing the server files' section) before starting this container." >&2
  echo "WARNING: continuing without the server binary - the dashboard will still start, but the game server can't run until this is fixed." >&2
fi

if server_present && [ "${AUTO_START:-true}" = "true" ]; then
  echo "AUTO_START=true, launching accServer.exe..."
  python3 /app/server_process.py start || echo "WARNING: automatic server start failed - use the dashboard to retry." >&2
elif [ "${AUTO_START:-true}" != "true" ]; then
  echo "AUTO_START=false, server left stopped. Start it from the dashboard."
fi

exec python3 /app/app.py
