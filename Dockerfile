FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEARCH=win64 \
    WINEPREFIX=/opt/wineprefix \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES=mscoree=d;mshtml=d \
    STEAMCMDDIR=/opt/steamcmd \
    ACC_INSTALL_DIR=/data/accserver \
    ACC_DATA_DIR=/data \
    ACC_CFG_DIR=/data/cfg \
    STEAM_HOME=/data/.steam_home

# --- OS deps: wine (via WineHQ, for a known-good 64-bit build) + steamcmd's
# 32-bit runtime deps + python for the dashboard --------------------------
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg2 \
        lib32gcc-s1 lib32stdc++6 \
        python3 python3-pip \
    && mkdir -pm755 /etc/apt/keyrings \
    && curl -fsSL https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key \
    && curl -fsSL -o /etc/apt/sources.list.d/winehq-jammy.sources https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources \
    && apt-get update \
    && apt-get install -y --install-recommends winehq-stable \
    && rm -rf /var/lib/apt/lists/*

# Initialize the Wine prefix at build time so the first container start
# doesn't pay for it. mscoree/mshtml are disabled above to skip the
# Mono/Gecko GUI installers, which would otherwise hang with no display.
RUN wineboot --init && wineserver --wait

# --- SteamCMD ---------------------------------------------------------------
# Just the tool itself - no credentials needed for this part. The actual ACC
# server download happens at container start (entrypoint.sh), against the
# persistent /data volume, because it needs a real (if free/disposable) Steam
# account, and that account's first-ever login needs a one-time interactive
# Steam Guard email code that no CI/build environment can answer. Doing the
# download at runtime means that one-time step happens once on the real host
# and is then remembered forever via /data, instead of on every CI build.
RUN mkdir -p ${STEAMCMDDIR} && \
    curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" \
        | tar zxvf - -C ${STEAMCMDDIR}

# --- dashboard app ------------------------------------------------------------
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY app/ /app/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080 9231/udp 9231/tcp
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
