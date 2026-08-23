"""Starts/stops the Windows-only accServer.exe under Wine, and lets the
dashboard tail its log. One process at a time, tracked via a pidfile."""
import glob
import os
import signal
import subprocess
import time

ACC_INSTALL_DIR = os.environ.get("ACC_INSTALL_DIR", "/opt/accserver")
DATA_DIR = os.environ.get("ACC_DATA_DIR", "/data")
PIDFILE = os.path.join(DATA_DIR, "server.pid")
LOGFILE = os.path.join(DATA_DIR, "logs", "server.log")
BIN_DIR_CACHE = os.path.join(DATA_DIR, ".bin_dir")


def find_bin_dir():
    """Locate the directory containing accServer.exe, caching the result
    since the depot layout only needs to be discovered once."""
    if os.path.exists(BIN_DIR_CACHE):
        with open(BIN_DIR_CACHE) as f:
            cached = f.read().strip()
        if cached and os.path.exists(os.path.join(cached, "accServer.exe")):
            return cached

    matches = glob.glob(os.path.join(ACC_INSTALL_DIR, "**", "accServer.exe"), recursive=True)
    if not matches:
        raise FileNotFoundError(
            f"accServer.exe not found under {ACC_INSTALL_DIR} - the SteamCMD "
            "download step may have failed at image build time."
        )
    bin_dir = os.path.dirname(matches[0])
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BIN_DIR_CACHE, "w") as f:
        f.write(bin_dir)
    return bin_dir


def _link_dir(target_name, bin_dir, real_dir):
    """Point bin_dir/target_name at the persistent volume so the game
    server and the dashboard always read/write the exact same files."""
    os.makedirs(real_dir, exist_ok=True)
    link_path = os.path.join(bin_dir, target_name)
    if os.path.abspath(link_path) == os.path.abspath(real_dir):
        # bin_dir IS the data dir (both mounted from the same host path) -
        # they're already the same directory, nothing to link.
        return
    if os.path.islink(link_path):
        if os.readlink(link_path) == real_dir:
            return
        os.remove(link_path)
    elif os.path.isdir(link_path):
        # first run against a fresh depot download - it ships its own
        # default cfg folder; nuke it in favor of the persistent one.
        import shutil
        shutil.rmtree(link_path)
    elif os.path.exists(link_path):
        os.remove(link_path)
    os.symlink(real_dir, link_path)


def prepare_bin_dir():
    bin_dir = find_bin_dir()
    _link_dir("cfg", bin_dir, os.path.join(DATA_DIR, "cfg"))
    _link_dir("results", bin_dir, os.path.join(DATA_DIR, "results"))
    _link_dir("log", bin_dir, os.path.join(DATA_DIR, "logs", "acc_internal"))
    return bin_dir


def _read_pid():
    if not os.path.exists(PIDFILE):
        return None
    try:
        with open(PIDFILE) as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def status():
    pid = _read_pid()
    return {"running": _alive(pid), "pid": pid}


def start():
    st = status()
    if st["running"]:
        return st

    bin_dir = prepare_bin_dir()
    os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

    env = os.environ.copy()
    env.setdefault("WINEARCH", "win64")
    env.setdefault("WINEDEBUG", "-all")
    env.setdefault("WINEPREFIX", "/opt/wineprefix")

    with open(LOGFILE, "ab") as logf:
        logf.write(f"\n--- starting accServer.exe at {time.ctime()} ---\n".encode())
        proc = subprocess.Popen(
            ["wine", "accServer.exe"],
            cwd=bin_dir,
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    with open(PIDFILE, "w") as f:
        f.write(str(proc.pid))
    return {"running": True, "pid": proc.pid}


def stop(timeout=15):
    pid = _read_pid()
    if not _alive(pid):
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
        return {"running": False, "pid": None}

    os.killpg(os.getpgid(pid), signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _alive(pid):
            break
        time.sleep(0.5)
    else:
        os.killpg(os.getpgid(pid), signal.SIGKILL)

    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)
    return {"running": False, "pid": None}


def restart():
    stop()
    time.sleep(1)
    return start()


def tail_log(n_lines=200):
    if not os.path.exists(LOGFILE):
        return "(no log output yet)"
    with open(LOGFILE, "rb") as f:
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    actions = {"start": start, "stop": stop, "restart": restart, "status": status}
    if cmd not in actions:
        print(f"usage: {sys.argv[0]} [start|stop|restart|status]")
        sys.exit(1)
    print(actions[cmd]())
