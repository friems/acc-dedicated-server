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
- `entrypoint.sh` - on container start: downloads the ACC dedicated
  server via SteamCMD into `/data/accserver` if it isn't there yet,
  ensures `/data/cfg` has default config (only if missing), optionally
  auto-starts the game server, then starts the dashboard.
- Everything persistent - `cfg/`, `results/`, `logs/`, the ACC server
  install itself, and SteamCMD's login session - lives in `/data`. That
  last part matters: it's what makes the one-time Steam login below a
  true one-time thing instead of something you redo on every rebuild.

## Steam account (needed to download the server)

Downloading the ACC dedicated server needs a real Steam account - a
free, disposable one is fine, it never needs to own or launch anything.
Anonymous SteamCMD login does **not** work for this specific app
(confirmed - it fails with "Missing configuration"; CubeCoders' AMP
template for this game explicitly sets `SteamUpdateAnonymousLogin=False`
too). Create one at store.steampowered.com, then go to **Account
Details > Manage Steam Guard account security > Steam Guard is turned
off** (fully off, not just the mobile authenticator - otherwise routine
logins would keep demanding a 2FA code).

Set `STEAM_USER` / `STEAM_PASSWORD` wherever you set the rest of this
project's settings (`.env`, or directly in the pasted YAML for the QNAP
GUI) - there's no default, it's required.

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
Container Station restart - just works with no further prompts.
Don't paste your Steam credentials into chat with me - they only belong
in your own `.env`/deployment config.

## First-time setup (Linux host, Docker CLI)

1. Copy `env.example` to `.env` and edit it:
   ```
   cp env.example .env
   ```
   At minimum, set `DATA_PATH`, `STEAM_USER`, and `STEAM_PASSWORD`
   (none have defaults, on purpose - see above), and change
   `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, and `FLASK_SECRET_KEY`. The
   rest (`SERVER_NAME`, `TRACK`, `CAR_GROUP`, ports, weather, ...) only
   seed the config the very first time the server starts (empty volume)
   - after that, use the dashboard.

2. Create the directory you chose for `DATA_PATH`, build, and do the
   one-time interactive download:
   ```
   mkdir -p /path/to/your/data-dir   # whatever you set DATA_PATH to
   docker compose build
   docker compose run --rm -it acc-server download-server
   ```
   Watch for a Steam Guard code prompt (see "Steam account" above) and
   enter it if asked. Once that finishes successfully:
   ```
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

3. **In Container Station's web UI**: Applications > Create > paste the
   contents of `docker-compose.yml` as-is (it already points at the GHCR
   image). Since the GUI won't read `.env`, edit values *directly in the
   pasted YAML* before creating the app:
   - `${DATA_PATH:?...}` - required, no default. Replace the whole
     `${DATA_PATH:?...}` expression with the literal path you created in
     step 2, e.g. `/share/Container/acc-server`.
   - `${STEAM_USER:?...}` / `${STEAM_PASSWORD:?...}` - required, no
     default. Replace with your disposable Steam account's credentials
     (see "Steam account" above).
   - `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY` - replace
     e.g. `${DASHBOARD_PASSWORD:-changeme}` with
     `${DASHBOARD_PASSWORD:-YourRealPassword}`, or just the literal
     value.

4. Start the application from Container Station. On this first start,
   `entrypoint.sh` will try the ACC server download and - almost
   certainly - fail, because Container Station starts it non-interactively
   and the very first Steam login needs that one-time interactive Guard
   code (see "Steam account" above). That's expected; the dashboard will
   still come up. Now do the one-time interactive step: over SSH,
   ```
   docker exec -it acc-server /entrypoint.sh download-server
   ```
   (or check whether your Container Station version has a per-container
   **Terminal/Console** tab in the container's detail view - if so, you
   can run that same command from there instead of SSH). Enter the Guard
   code if Steam emails you one.

5. Once that succeeds, restart the application from Container Station so
   `entrypoint.sh` finds the now-downloaded server and starts it. Open
   `http://<nas-ip>:8080`, log in, and check the log panel to confirm
   `accServer.exe` actually came up under Wine.

6. Forward TCP+UDP `9231` (or whatever you set) on your router, pointing
   at the NAS's IP.

**Updating the dashboard/image later**: push a commit (or re-run the
workflow manually from the Actions tab), wait for it to publish a new
`:latest`, then in Container Station either restart the application (if
it's set to always pull) or remove/recreate it to force a fresh pull -
your `/data` (config, Steam login, the ACC server itself) is untouched
either way. **Updating the ACC server version itself** needs its
contents refreshed: delete `<DATA_PATH>/accserver`'s contents via File
Station, then repeat the interactive `download-server` step above (no
new Guard code needed - that session is still cached in
`<DATA_PATH>/.steam_home`).

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
You'll still do the one-time interactive `download-server` step from
the "Steam account" section either way - that's a runtime step, not a
build one, so it applies regardless of how the image itself was built.

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
- To update the ACC server itself (not the image/dashboard), delete
  `<DATA_PATH>/accserver`'s contents and re-run the `download-server`
  step (see the QNAP or first-time-setup sections) - it won't ask for a
  Guard code again, that session is already cached.
- Logs: the dashboard tails the last ~200 lines live; the full log is at
  `/data/logs/server.log` inside the container, i.e.
  `<DATA_PATH>/logs/server.log` on the host.
- If you'd previously added `STEAM_USER`/`STEAM_PASSWORD` as **GitHub
  Actions** repo secrets (from an earlier iteration of this setup), they
  can be deleted - the build no longer uses them. They're only needed as
  regular deployment config now (`.env` / the pasted `docker-compose.yml`
  on the NAS), for the runtime download in `entrypoint.sh`.
