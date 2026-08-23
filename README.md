# ACC Dedicated Server (Docker)

Runs a dedicated **Assetto Corsa Competizione** multiplayer server in a
container (the server binary is Windows-only, so it runs under Wine), with
a small web dashboard for changing settings - track, weather, server name,
passwords, car group, session lengths, and a few advanced race/assist
rules - without touching JSON by hand.

## How it's put together

- `Dockerfile` - Ubuntu 22.04 + Wine (WineHQ stable, 64-bit) + the
  SteamCMD tool itself. It does **not** download the ACC server or need
  any Steam credentials at build time - see below for why.
- `app/` - a small Flask app (served via waitress) that is the only thing
  that runs in the foreground. It reads/writes ACC's `cfg/*.json` files
  (UTF-16LE + BOM, as ACC requires) and starts/stops `wine accServer.exe`
  as a child process.
- `entrypoint.sh` - on container start: looks for the ACC dedicated
  server under `/data/accserver` (normally supplied via the
  `ACC_SERVER_PATH` mount, see below); if it's genuinely missing, falls
  back to downloading it via SteamCMD; either way it then ensures
  `/data/cfg` has default config (only if missing), optionally
  auto-starts the game server, then starts the dashboard.
- Everything persistent - `cfg/`, `results/`, `logs/`, and (if you use
  the SteamCMD fallback) its login session - lives in `/data`. The ACC
  server install itself lives separately, under whatever host path you
  point `ACC_SERVER_PATH` at.

## Providing the server files (recommended)

The ACC dedicated server binaries don't need to be downloaded by the
container at all - you can fetch them once, anywhere you like (another
PC, the NAS itself over SSH, a VM), and just point the container at that
folder. This sidesteps SteamCMD's interactive Steam Guard step entirely
inside the container, which is what used to make Container Station's
non-interactive first start fail.

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

## Steam account (optional fallback - only if you skip the above)

If you'd rather have the *container* download the server itself instead
of feeding it in via `ACC_SERVER_PATH`, set `STEAM_USER` / `STEAM_PASSWORD`
wherever you set the rest of this project's settings (`.env`, or directly
in the pasted YAML for the QNAP GUI) - both default to blank/unused.
Anonymous SteamCMD login does **not** work for this specific app
(confirmed - it fails with "Missing configuration"; CubeCoders' AMP
template for this game explicitly sets `SteamUpdateAnonymousLogin=False`
too). Create one at store.steampowered.com, then go to **Account
Details > Manage Steam Guard account security > Steam Guard is turned
off** (fully off, not just the mobile authenticator - otherwise routine
logins would keep demanding a 2FA code).

**Even with Steam Guard off, the very first login from a brand-new
"device" (i.e. this container, the first time it ever runs) still gets a
one-time email verification code from Steam** - this is a base Valve
security check, separate from the Guard toggle, and there is no way to
script around it. So the first time only, you run the download as an
interactive step so you can see the prompt and type the code:
```
docker compose run --rm -it acc-server download-server
```
If Steam emails a code, paste it in when steamcmd asks. That session is
then cached under `/data/.steam_home` (on your persistent volume), so
every normal start after that - `docker compose up -d`, a NAS reboot, a
Container Station restart - just works with no further prompts. This is
exactly the interactive-login problem `ACC_SERVER_PATH` above avoids -
prefer that route on a NAS/Container Station where you can't easily
attach an interactive terminal.
Don't paste your Steam credentials into chat with me - they only belong
in your own `.env`/deployment config.

## First-time setup (Linux host, Docker CLI)

1. Copy `env.example` to `.env` and edit it:
   ```
   cp env.example .env
   ```
   At minimum, set `DATA_PATH` and `ACC_SERVER_PATH` (see "Providing the
   server files" above - neither has a default, on purpose), and change
   `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, and `FLASK_SECRET_KEY`. Leave
   `STEAM_USER`/`STEAM_PASSWORD` blank unless you're using the SteamCMD
   fallback instead. The rest (`SERVER_NAME`, `TRACK`, `CAR_GROUP`, ports,
   weather, ...) only seed the config the very first time the server
   starts (empty volume) - after that, use the dashboard.

2. Create the `DATA_PATH` directory, populate `ACC_SERVER_PATH` (see
   "Providing the server files" above), build, and start:
   ```
   mkdir -p /path/to/your/data-dir   # whatever you set DATA_PATH to
   docker compose build
   docker compose up -d
   ```

3. Open the dashboard at `http://<host>:8080` (default port, see
   `DASHBOARD_PORT` in `.env`) and log in with `DASHBOARD_USER`/
   `DASHBOARD_PASSWORD`.

4. Forward/open these ports on your router/firewall for players to
   actually reach the server: `TCP_PORT` and `UDP_PORT` (both default to
   `9231`), for both TCP and UDP.

## Deploying on a QNAP NAS (Container Station)

This was built and tuned for exactly this use case, on x86_64 QNAP models
(Container Station requires x86_64 for Wine/SteamCMD - it will not work
on ARM-based QNAP models).

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
   - `${STEAM_USER:-}` / `${STEAM_PASSWORD:-}` - leave as-is (blank) if
     you're providing server files via `ACC_SERVER_PATH`; only fill these
     in if you want the SteamCMD fallback instead (see "Steam account"
     above) - note that route needs an interactive Guard-code step below
     that `ACC_SERVER_PATH` avoids entirely.
   - `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY` - replace
     e.g. `${DASHBOARD_PASSWORD:-changeme}` with
     `${DASHBOARD_PASSWORD:-YourRealPassword}`, or just the literal
     value.

5. Start the application from Container Station. `entrypoint.sh` finds
   `accServer.exe` under the `ACC_SERVER_PATH` mount immediately, so no
   further interactive step is needed - it should come straight up. Open
   `http://<nas-ip>:8080`, log in, and check the log panel to confirm
   `accServer.exe` actually came up under Wine.

   (If you went with the SteamCMD fallback instead of `ACC_SERVER_PATH`,
   this first start will fail to download non-interactively - that's
   expected; the dashboard still comes up. Do the one-time interactive
   step over SSH: `docker exec -it acc-server /entrypoint.sh
   download-server` (or your Container Station version's per-container
   **Terminal/Console** tab, if it has one), enter the Guard code if
   Steam emails you one, then restart the application.)

6. Forward TCP+UDP `9231` (or whatever you set) on your router, pointing
   at the NAS's IP.

**Updating the dashboard/image later**: push a commit (or re-run the
workflow manually from the Actions tab), wait for it to publish a new
`:latest`, then in Container Station either restart the application (if
it's set to always pull) or remove/recreate it to force a fresh pull -
your `/data` (config, and Steam login if you use the SteamCMD fallback)
and your `ACC_SERVER_PATH` folder are untouched either way. **Updating
the ACC server version itself**: re-run the `steamcmd ...
+app_update 1430110 validate +quit` command from "Providing the server
files" against your `ACC_SERVER_PATH` folder, then restart the
application so `entrypoint.sh` picks up the refreshed files.

**Resource note**: ACC's dedicated server itself is lightweight (it's a
headless simulation, not rendering anything), so a small/private server
(a handful of drivers) should run fine even on modest QNAP CPUs (Celeron/
Pentium). Wine adds some overhead on top; if you're on the lowest-end
QNAP models, keep an eye on CPU load once players connect.

### If you'd rather not use GitHub Actions

Everything above also still works the old way - SSH into the NAS, `git
clone` this repo (or copy the files over), then `docker build -t
acc-dedicated-server:latest .` (no Steam credentials needed for this
part anymore) and point `docker-compose.yml`'s `image:` at that local
tag instead of the GHCR one before pasting it into Container Station.
You'll still need `ACC_SERVER_PATH` pointed at a populated server-files
folder (or the interactive `download-server` fallback) either way -
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
- The dashboard has no HTTPS/TLS of its own. Don't expose port 8080
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
  Actions** repo secrets (from an earlier iteration of this setup), they
  can be deleted - the build no longer uses them. They're only needed as
  regular deployment config now (`.env` / the pasted `docker-compose.yml`
  on the NAS), and only if you're using the SteamCMD fallback instead of
  `ACC_SERVER_PATH`.
