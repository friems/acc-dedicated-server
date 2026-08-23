#!/bin/bash
set -uo pipefail

ACC_INSTALL_DIR="${ACC_INSTALL_DIR:-/data/accserver}"
STEAM_HOME="${STEAM_HOME:-/data/.steam_home}"

mkdir -p /data/cfg /data/results /data/logs "$ACC_INSTALL_DIR" "$STEAM_HOME"

server_present() {
  find "$ACC_INSTALL_DIR" -iname accServer.exe 2>/dev/null | grep -q .
}

# Preferred path: mount pre-downloaded server files (accServer.exe etc)
# via ACC_SERVER_PATH -> /data/accserver (see docker-compose.yml / README's
# "Providing the server files" section) - server_present() below finds
# them and this function is never needed.
#
# Fallback path: downloads the ACC dedicated server via SteamCMD into the
# persistent /data volume. The FIRST time this specific Steam account logs
# in from this container, Steam emails a Guard code and steamcmd blocks
# waiting for it on stdin - that only works with an interactive terminal
# attached (`docker compose run --rm -it acc-server download-server`). Once
# that one-time login succeeds, its session is cached under $STEAM_HOME
# (which lives on the persistent volume), so every run after that -
# including normal, non-interactive container starts - just works.
download_server() {
  if server_present; then
    echo "ACC server already present in ${ACC_INSTALL_DIR} - skipping download."
    return 0
  fi
  if [ -z "${STEAM_USER:-}" ] || [ -z "${STEAM_PASSWORD:-}" ]; then
    echo "ERROR: no ACC server found in ${ACC_INSTALL_DIR}, and STEAM_USER / STEAM_PASSWORD are not set." >&2
    echo "Either mount pre-downloaded server files via ACC_SERVER_PATH (see README's" >&2
    echo "'Providing the server files' section), or set STEAM_USER/STEAM_PASSWORD (see" >&2
    echo "README's 'Steam account' section) and run:" >&2
    echo "  docker compose run --rm -it acc-server download-server" >&2
    return 1
  fi
  echo "Downloading the ACC dedicated server via SteamCMD (app 1430110)..."
  echo "If this account has never logged in from here before, Steam will email"
  echo "a Guard code and steamcmd will wait for it below - this requires an"
  echo "interactive terminal (docker compose run --rm -it acc-server download-server)."
  HOME="$STEAM_HOME" /opt/steamcmd/steamcmd.sh \
    +@sSteamCmdForcePlatformType windows \
    +force_install_dir "$ACC_INSTALL_DIR" \
    +login "$STEAM_USER" "$STEAM_PASSWORD" \
    +app_update 1430110 validate \
    +quit
}

# `docker compose run --rm -it acc-server download-server` - just do the
# (possibly interactive) download and exit, skip the dashboard/game server.
if [ "${1:-}" = "download-server" ]; then
  download_server
  exit $?
fi

python3 -c "import sys; sys.path.insert(0, '/app'); import acc_config; acc_config.ensure_defaults()"

if ! server_present; then
  echo "ACC server not yet downloaded."
  download_server || echo "WARNING: continuing without the server binary - the dashboard will still start, but the game server can't run until this is fixed." >&2
fi

if server_present && [ "${AUTO_START:-true}" = "true" ]; then
  echo "AUTO_START=true, launching accServer.exe..."
  python3 /app/server_process.py start || echo "WARNING: automatic server start failed - use the dashboard to retry." >&2
elif [ "${AUTO_START:-true}" != "true" ]; then
  echo "AUTO_START=false, server left stopped. Start it from the dashboard."
fi

exec python3 /app/app.py
