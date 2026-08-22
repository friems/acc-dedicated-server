# ACC Dedicated Server (Docker)

Runs a dedicated **Assetto Corsa Competizione** multiplayer server in a
container (the server binary is Windows-only, so it runs under Wine), with
a small web dashboard for changing settings - track, weather, server name,
passwords, car group, session lengths, and a few advanced race/assist
rules - without touching JSON by hand.

## How it's put together

- `Dockerfile` - Ubuntu 22.04 + Wine (WineHQ stable, 64-bit) + SteamCMD.
  At build time, SteamCMD downloads the ACC dedicated server (Steam app
  id `1430110`, Windows depot). Anonymous SteamCMD login does **not**
  work for this specific app (confirmed - it fails with "Missing
  configuration"; even Kunos requires a real, if free, account for it),
  so the build needs Steam credentials for a real account - see
  "Steam account for the build" below. Credentials are passed as Docker
  BuildKit secrets, never baked into an image layer.
- `app/` - a small Flask app (served via waitress) that is the only thing
  that runs in the foreground. It reads/writes ACC's `cfg/*.json` files
  (UTF-16LE + BOM, as ACC requires) and starts/stops `wine accServer.exe`
  as a child process.
- `entrypoint.sh` - on container start: ensures `/data/cfg` has default
  config (only if missing), optionally auto-starts the game server, then
  starts the dashboard.
- Everything persistent (`cfg/`, `results/`, `logs/`) lives in `/data`,
  which is symlinked into the server's install directory so the dashboard
  and the game server are always looking at the same files.

## Steam account for the build

Building the image (either locally or via GitHub Actions) needs a real
Steam account to download the ACC dedicated server - a free, disposable
one is fine, it never needs to own or launch anything. Create one at
store.steampowered.com, then go to **Account Details > Manage Steam
Guard account security > Steam Guard is turned off**. This has to be
fully off (not just the mobile authenticator) or the headless/CI login
will get stuck waiting on a 2FA code nobody can answer.

**For GitHub Actions**: add the credentials as repo secrets so the
workflow can use them - go to your repo's **Settings > Secrets and
variables > Actions > New repository secret** and add:
- `STEAM_USER` - the account's username
- `STEAM_PASSWORD` - the account's password

Don't paste these into chat with me or commit them anywhere - the whole
point of BuildKit secrets is that they only ever live in GitHub's secret
store and the ephemeral build container.

**For a local/SSH build** (see the QNAP section's "if you'd rather not
use GitHub Actions" note), create two small files instead - they're
already covered by `.gitignore`:
```
mkdir -p secrets
echo -n "your-steam-username" > secrets/steam_user.txt
echo -n "your-steam-password" > secrets/steam_password.txt
docker compose build
```

## First-time setup (Linux host, Docker CLI)

1. Copy `env.example` to `.env` and edit it:
   ```
   cp env.example .env
   ```
   At minimum, set `DATA_PATH` (there's no default, on purpose - see
   below) and change `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, and
   `FLASK_SECRET_KEY`. The rest (`SERVER_NAME`, `TRACK`, `CAR_GROUP`,
   ports, weather, ...) only seed the config the very first time the
   server starts (empty volume) - after that, use the dashboard.

2. Create `secrets/steam_user.txt` and `secrets/steam_password.txt` (see
   "Steam account for the build" above), and the directory you chose for
   `DATA_PATH`, then build and start:
   ```
   mkdir -p /path/to/your/data-dir   # whatever you set DATA_PATH to
   docker compose up -d --build
   ```
   The first build takes a while (installs Wine + downloads the ~1GB+
   server via SteamCMD).

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
   - `DASHBOARD_PASSWORD`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY` - replace
     e.g. `${DASHBOARD_PASSWORD:-changeme}` with
     `${DASHBOARD_PASSWORD:-YourRealPassword}`, or just the literal
     value.

4. Start the application from Container Station, then open
   `http://<nas-ip>:8080`, log in, and check the log panel to confirm
   `accServer.exe` actually came up under Wine.

5. Forward TCP+UDP `9231` (or whatever you set) on your router, pointing
   at the NAS's IP.

**Updating the server later**: push a commit (or re-run the workflow
manually from the Actions tab), wait for it to publish a new `:latest`,
then in Container Station either restart the application (if it's set to
always pull) or remove/recreate it to force a fresh pull.

**Resource note**: ACC's dedicated server itself is lightweight (it's a
headless simulation, not rendering anything), so a small/private server
(a handful of drivers) should run fine even on modest QNAP CPUs (Celeron/
Pentium). Wine adds some overhead on top; if you're on the lowest-end
QNAP models, keep an eye on CPU load once players connect.

### If you'd rather not use GitHub Actions

Everything above also still works the old way - SSH into the NAS, `git
clone` this repo (or copy the files over), create `secrets/steam_user.txt`
and `secrets/steam_password.txt` (see "Steam account for the build"
above), then:
```
docker build --secret id=steam_user,src=secrets/steam_user.txt \
             --secret id=steam_password,src=secrets/steam_password.txt \
             -t acc-dedicated-server:latest .
```
and point `docker-compose.yml`'s `image:` at that local tag instead of
the GHCR one before pasting it into Container Station.

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
- To update the ACC server itself, rebuild the image (`docker compose
  build --no-cache`) so SteamCMD re-runs `app_update`.
- Logs: the dashboard tails the last ~200 lines live; the full log is at
  `/data/logs/server.log` inside the container, i.e.
  `<DATA_PATH>/logs/server.log` on the host.
