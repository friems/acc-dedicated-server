#!/bin/bash
set -euo pipefail

mkdir -p /data/cfg /data/results /data/logs

python3 -c "import sys; sys.path.insert(0, '/app'); import acc_config; acc_config.ensure_defaults()"

if [ "${AUTO_START:-true}" = "true" ]; then
  echo "AUTO_START=true, launching accServer.exe..."
  python3 /app/server_process.py start || echo "WARNING: automatic server start failed - use the dashboard to retry." >&2
else
  echo "AUTO_START=false, server left stopped. Start it from the dashboard."
fi

exec python3 /app/app.py
