FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WINEARCH=win64 \
    WINEPREFIX=/opt/wineprefix \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES=mscoree=d;mshtml=d \
    ACC_INSTALL_DIR=/data/accserver \
    ACC_DATA_DIR=/data \
    ACC_CFG_DIR=/data/cfg

# --- OS deps: wine (via WineHQ, for a known-good 64-bit build) + python
# for the dashboard ----------------------------------------------------------
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
