# ACC Dedicated Server (Docker)

Runs a dedicated **Assetto Corsa Competizione** multiplayer server in a
container (the server binary is Windows-only, so it runs under Wine), with
a small web dashboard for changing settings - track, weather, server name,
passwords, car group, session lengths, and a few advanced race/assist
rules - without touching JSON by hand.

## How it's put together

- `Dockerfile` - Ubuntu 22.04 + Wine (WineHQ stable, 64-bit), for running
  the Windows-only `accServer.exe` binary. It does **not** download the
  ACC server itself, and needs no Steam credentials at all - see below.
- `app/` - a small Flask app (served via waitress) that is the only thing
  that runs in the foreground. It reads/writes ACC's `cfg/*.json` files
  (UTF-16LE + BOM, as ACC requires) and starts/stops `wine accServer.exe`
  as a child process.
- `entrypoint.sh` - on container start: looks for the ACC dedicated
  server under `/data/accserver` (supplied via the `ACC_SERVER_PATH`
  mount, see below); ensures `/data/cfg` has default config (only if
  missing); optionally auto-starts the game server; then starts the
  dashboard.
- Everything persistent - `cfg/`, `results/`, `logs/` - lives in `/data`.
  The ACC server install itself lives separately, under whatever host
  path you point `ACC_SERVER_PATH` at.

## Providing the server files (required)

The ACC dedicated server binaries aren't downloaded by the container at
all - you fetch them once, anywhere you like (another PC, the NAS itself
over SSH, a VM), and just point the container at that folder.

1. On any machine with `steamcmd` installed (a free/disposable Steam
   account is fine - anonymous login does **not** work for this specific
   app, confirmed, it fails with "Missing configuration"), run:
   ```
   steamcmd +@sSteamCmdForcePlatformType windows \
     +force_install_dir /path/to/ACCServerFiles \
     +login YOUR_STEAM_USER YOUR_STEAM_PASSWORD \
     +app_update 1430110 validate \
     +quit
   ```
   The very first login from a new device may prompt for a one-time
   Steam Guard email code - steamcmd waits for it on stdin, so run this
   interactively the first time. This is a one-off step on whatever
   machine you use to fetch the files; it has nothing to do with the
   container.
2. Copy/rsync the resulting `ACCServerFiles` folder (it should contain
   `accServer.exe`) onto the NAS share you want the container to read
   from, e.g. `/share/ACCServerFiles`.
3. Set `ACC_SERVER_PATH` (in `.env`, or directly in the pasted YAML for
   the QNAP GUI) to that folder - there's no default, it's required. The
   container bind-mounts it straight to `/data/accserver`.
4. To update the server later (new ACC patch), just re-run the same
   `steamcmd ... +app_update 1430110 validate +quit` command against the
   same folder, no container changes needed - `entrypoint.sh` finds
   whatever's there on the next start.

## Network

The container is attached directly to a pre-existing bridged/macvlan-style
docker network (e.g. a QNAP Container Station "virtual switch") instead of
docker's default NAT bridge, and given a fixed MAC address. This means the
container gets its own real IP on the LAN via DHCP, and there's no
host-side port mapping (`ports:` in `docker-compose.yml`) - the dashboard
and game server ports are reached directly at the container's own IP.

This matters because docker's default NAT + port-publishing is a common
cause of a server that shows as "started" in the dashboard but can't be
found in-game: NAT/UDP hairpinning can silently break lobby registration
or connectivity even though the process itself is running fine. Giving
the container its own routable LAN IP sidesteps that entirely.

Set these (both required, no default) in `.env` (or directly in the
pasted YAML for the QNAP GUI):
- `ACC_NETWORK_NAME` - the name of your pre-existing bridged network
  (QNAP: Container Station > Network > find/create a "Bridge" mode virtual
  switch, named something like `qnet-dhcp-eth0-xxxxxx`).
- `ACC_MAC_ADDRESS` - a fixed MAC address for the container, so it
  reliably gets the same DHCP lease/IP across restarts.

`DASHBOARD_PORT`, `TCP_PORT`, and `UDP_PORT` are then the container's own
listen ports directly (no separate host-side port) - browse to
`http://<container-ip>:<DASHBOARD_PORT>`, and forward `TCP_PORT`/
`UDP_PORT` on your router to that same container IP.

If you don't have a network like this set up and just want the classic
docker NAT + published-ports model instead, replace the `mac_address:`/
`networks:` blocks in `docker-compose.yml` with a `ports:` block mapping
`${DASHBOARD_PORT:-8080}:8080`, `${TCP_PORT:-9231}:${TCP_PORT:-9231}/tcp`,
and `${UDP_PORT:-9231}:${UDP_PORT:-9231}/udp` - just note that setup is
more prone to the in-game visibility issue described above.

## First-time setup (Linux host, Docker CLI)

1. Copy `env.example` to `.env` and edit it:
   ```
   cp env.example .env
   ```
   At minimum, set `DATA_PATH`, `ACC_SERVER_PATH` (see "Providing the
   server files" above), `ACC_NETWORK_NAME`, and `ACC_MAC_ADDRESS` (see
   "Network" above - none of these have a default, on purpose), and
   change `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, and `FLASK_SECRET_KEY`.
   The rest (`SERVER_NAME`, `TRACK`, `CAR_GROUP`, ports, weather, ...)
   only seed the config the very first time the server starts (empty
   volume) - after that, use the dashboard.

2. Create the `DATA_PATH` directory, populate `ACC_SERVER_PATH` (see
   "Providing the server files" above), build, and start:
   ```
   mkdir -p /path/to/your/data-dir   # whatever you set DATA_PATH to
   docker compose build
   docker compose up -d
   ```

3. Open the dashboard at `http://<container-ip>:<DASHBOARD_PORT>` (see
   "Network" above) and log in with `DASHBOARD_USER`/`DASHBOARD_PASSWORD`.

4. Forward/open `TCP_PORT` and `UDP_PORT` on your router/firewall,
   pointed at the container's own IP, for players to actually reach the
   server.

## Deploying on a QNAP NAS (Container Station)

This was built and tuned for exactly this use case, on x86_64 QNAP models
(Container Station requires x86_64 for Wine - it will not work on
ARM-based QNAP models).

The image is built automatically by [GitHub Actions](.github/workflows/docker-publish.yml)
on every push to `main`, and published to GHCR at
`ghcr.io/friems/acc-dedicated-server:latest`. That means Container
Station's GUI **"Create Application"** importer - which only runs a
pre-built `image:` and can't build a `Dockerfile` itself - can just pull
it directly. No SSH, no local build, on the NAS at all.

1. **One-time**: make the GHCR package public, otherwise Container
   Station's pull will get a 403. After the first successful Actions run,
   go to your GitHub profile > Packages > `acc-dedicated-server` >
   Package settings (bottom of the page) > Change visibility > Public.
   (New GHCR packages default to private even when the source repo is
   public - this is a one-off GitHub quirk, not something the workflow
   can set for you.)

2. **Create a data folder** via File Station, e.g. `Container/acc-server`
   (i.e. `/share/Container/acc-server`) - anywhere you like, as long as
   it's visible/backupable from the NAS UI. There's no default folder
   baked into `docker-compose.yml`; you choose the path in the next step.

3. **Populate a server-files folder** per "Providing the server files"
   above - run `steamcmd` on any machine you like (doesn't have to be the
   NAS), then copy the resulting folder onto a NAS share, e.g. File
   Station's `/share/ACCServerFiles`.

4. **In Container Station's web UI**: Applications > Create > paste the
   contents of `docker-compose.yml` as-is (it already points at the GHCR
   image). Since the GUI won't read `.env`, edit values *directly in the
   pasted YAML* before creating the app:
   - `${DATA_PATH:?...}` - required, no default. Replace the whole
     `${DATA_PATH:?...}` expression with the literal path you created in
     step 2, e.g. `/share/Container/acc-server`.
   - `${ACC_SERVER_PATH:?...}` - required, no default. Replace the whole
     expression with the literal path from step 3, e.g.
     `/share/ACCServerFiles`.
   - `${ACC_NETWORK_NAME:?...}` / `${ACC_MAC_ADDRESS:?...}` - required, no
     default. See "Network" above for how to create/find the network name
     in Container Station; the MAC can be any fixed address you like.
   - `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY` - replace
     e.g. `${DASHBOARD_PASSWORD:-changeme}` with
     `${DASHBOARD_PASSWORD:-YourRealPassword}`, or just the literal
     value.

5. Start the application from Container Station. `entrypoint.sh` finds
   `accServer.exe` under the `ACC_SERVER_PATH` mount immediately, so it
   should come straight up. Open `http://<container-ip>:<DASHBOARD_PORT>`
   (see "Network" above for how to find the container's IP), log in, and
   check the log panel to confirm `accServer.exe` actually came up under
   Wine.

6. Forward TCP+UDP `TCP_PORT`/`UDP_PORT` (or whatever you set) on your
   router, pointing at the container's own IP (see "Network" above).

**Updating the dashboard/image later**: push a commit (or re-run the
workflow manually from the Actions tab), wait for it to publish a new
`:latest`, then in Container Station either restart the application (if
it's set to always pull) or remove/recreate it to force a fresh pull -
your `/data` config and your `ACC_SERVER_PATH` folder are untouched
either way. **Updating the ACC server version itself**: re-run the
`steamcmd ... +app_update 1430110 validate +quit` command from
"Providing the server files" against your `ACC_SERVER_PATH` folder, then
restart the application so `entrypoint.sh` picks up the refreshed files.

**Resource note**: ACC's dedicated server itself is lightweight (it's a
headless simulation, not rendering anything), so a small/private server
(a handful of drivers) should run fine even on modest QNAP CPUs (Celeron/
Pentium). Wine adds some overhead on top; if you're on the lowest-end
QNAP models, keep an eye on CPU load once players connect.

### If you'd rather not use GitHub Actions

Everything above also still works the old way - SSH into the NAS, `git
clone` this repo (or copy the files over), then `docker build -t
acc-dedicated-server:latest .` (no Steam credentials needed at all) and
point `docker-compose.yml`'s `image:` at that local tag instead of the
GHCR one before pasting it into Container Station. You'll still need
`ACC_SERVER_PATH` pointed at a populated server-files folder either way -
that's a runtime concern, not a build one, so it applies regardless of
how the image itself was built.

## Changing settings

Everything in the dashboard - server name, passwords, track, car group,
weather (cloud/rain/randomness), session durations/times, and the
advanced pitstop/assist rules - is saved straight into the config files
ACC reads. **Settings changes take effect on the server's next restart**
(hit *Restart* in the dashboard after saving).

Two things the dashboard intentionally does *not* manage, because they're
advanced/rarely-touched league features:
- `entrylist.json` (reserved slots, forced cars, driver categories) - edit
  it directly at `<DATA_PATH>/cfg/entrylist.json` on the host (e.g.
  `/share/Container/acc-server/cfg/entrylist.json` on QNAP). It must stay
  UTF-16LE with a BOM - re-save through a script or `iconv`, not a plain
  text editor, or the server will silently misread it.
- `bop.json` (custom balance-of-performance) - same deal, hand-edited,
  same folder.

## Notes / gotchas

- Running under Wine is the standard (if unofficial) way ACC dedicated
  servers run on Linux - Kunos ships Windows binaries only. This is the
  same approach used by community projects like `grimsi/accserver-docker`
  and `gotzl/accservermanager`.
- The dashboard has no HTTPS/TLS of its own. Don't expose its port
  directly to the internet - put it behind a reverse proxy with TLS, or
  keep it on a VPN/LAN, since it can start/stop your server and holds
  your admin password.
- To update the ACC server itself (not the image/dashboard), re-run the
  `steamcmd ... +app_update 1430110 validate +quit` command from
  "Providing the server files" against your `ACC_SERVER_PATH` folder and
  restart the container - no in-container step needed.
- Logs: the dashboard tails the last ~200 lines live; the full log is at
  `/data/logs/server.log` inside the container, i.e.
  `<DATA_PATH>/logs/server.log` on the host.
- If you'd previously added `STEAM_USER`/`STEAM_PASSWORD` as **GitHub
  Actions** repo secrets or deployment env vars (from an earlier
  iteration of this setup that could download the server itself via
  SteamCMD), they can be deleted - that fallback has been removed
  entirely; `ACC_SERVER_PATH` is now the only way to supply the server
  binaries.
