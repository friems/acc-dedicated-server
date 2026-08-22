import functools
import os

from flask import Flask, redirect, render_template, request, session, url_for, jsonify

import acc_config as cfg
import server_process as proc

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")

DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")

# --- (section, key-within-file, label, type, extra) -------------------------
# "extra" holds widget-specific bits: options for select, min/max/step for
# number/float, help text shown under the field.
FIELD_SCHEMA = [
    ("Server identity", "settings", "serverName", "Server name", "text", {}),
    ("Server identity", "settings", "adminPassword", "Admin password", "password",
     {"help": "Needed in-game via /admin <password> to use race-control commands."}),
    ("Server identity", "settings", "password", "Join password", "password",
     {"help": "Leave blank for a public/open server."}),
    ("Server identity", "settings", "spectatorPassword", "Spectator password", "password", {}),

    ("Network", "configuration", "tcpPort", "TCP port", "number", {"min": 1, "max": 65535}),
    ("Network", "configuration", "udpPort", "UDP port", "number", {"min": 1, "max": 65535}),
    ("Network", "configuration", "maxConnections", "Max connections", "number", {"min": 1, "max": 200}),
    ("Network", "settings", "maxCarSlots", "Max car slots", "number", {"min": 1, "max": 82,
     "help": "Capped by the track's pit count. The gap vs. max connections is spectator slots."}),
    ("Network", "configuration", "registerToLobby", "List on public server list", "checkbox", {}),
    ("Network", "configuration", "lanDiscovery", "Respond to LAN discovery", "checkbox", {}),

    ("Track & session", "event", "track", "Track", "select", {"options": cfg.TRACKS}),
    ("Track & session", "settings", "carGroup", "Car group", "select", {"options": cfg.CAR_GROUPS}),
    ("Track & session", "settings", "trackMedalsRequirement", "Required track medals", "number", {"min": 0, "max": 3}),
    ("Track & session", "settings", "safetyRatingRequirement", "Min. Safety Rating (-1 = off)", "number", {"min": -1, "max": 99}),
    ("Track & session", "settings", "racecraftRatingRequirement", "Min. Racecraft Rating (-1 = off)", "number", {"min": -1, "max": 99}),

    ("Weather", "event", "ambientTemp", "Ambient temperature (°C)", "number", {"min": -10, "max": 40}),
    ("Weather", "event", "cloudLevel", "Cloud level", "float", {"min": 0, "max": 1, "step": 0.1}),
    ("Weather", "event", "rain", "Rain baseline", "float", {"min": 0, "max": 1, "step": 0.1}),
    ("Weather", "event", "weatherRandomness", "Weather randomness", "number", {"min": 0, "max": 7,
     "help": "0 = static weather. 1-4 realistic. 5-7 sensational/stormy."}),

    ("Race rules (advanced)", "eventRules", "mandatoryPitstopCount", "Mandatory pitstops", "number", {"min": 0, "max": 10}),
    ("Race rules (advanced)", "eventRules", "pitWindowLengthSec", "Pit window length, sec (-1 = off)", "number", {"min": -1, "max": 36000}),
    ("Race rules (advanced)", "eventRules", "isRefuellingAllowedInRace", "Refuelling allowed in race", "checkbox", {}),
    ("Race rules (advanced)", "eventRules", "isMandatoryPitstopRefuellingRequired", "Mandatory pitstop needs refuelling", "checkbox", {}),
    ("Race rules (advanced)", "eventRules", "isMandatoryPitstopTyreChangeRequired", "Mandatory pitstop needs tyre change", "checkbox", {}),
    ("Race rules (advanced)", "settings", "allowAutoDQ", "Auto-disqualify instead of stop&go", "checkbox", {}),

    ("Assists (advanced)", "assistRules", "stabilityControlLevelMax", "Max stability control %", "number", {"min": 0, "max": 100}),
    ("Assists (advanced)", "assistRules", "disableAutosteer", "Disable autosteer (gamepad aid)", "checkbox", {}),
    ("Assists (advanced)", "assistRules", "disableIdealLine", "Disable ideal racing line", "checkbox", {}),
    ("Assists (advanced)", "assistRules", "disableAutoPitLimiter", "Disable auto pit limiter", "checkbox", {}),
]

SESSION_FIELDS = ["sessionDurationMinutes", "hourOfDay", "dayOfWeekend", "timeMultiplier"]


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == DASHBOARD_USER and request.form.get("password") == DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@login_required
def index():
    config = cfg.load_all()
    sections = {}
    for section, file_, key, label, type_, extra in FIELD_SCHEMA:
        sections.setdefault(section, []).append({
            "id": f"{file_}.{key}",
            "file": file_,
            "key": key,
            "label": label,
            "type": type_,
            "value": config[file_].get(key, ""),
            **extra,
        })

    sessions_by_type = {s["sessionType"]: s for s in config["event"].get("sessions", [])}

    return render_template(
        "index.html",
        sections=sections,
        session_types=cfg.SESSION_TYPES,
        sessions_by_type=sessions_by_type,
        session_fields=SESSION_FIELDS,
        status=proc.status(),
    )


def _coerce(type_, raw):
    if type_ == "checkbox":
        return 1 if raw else 0
    if type_ == "number":
        return int(raw)
    if type_ == "float":
        return float(raw)
    return raw


@app.route("/save", methods=["POST"])
@login_required
def save():
    config = cfg.load_all()

    for section, file_, key, label, type_, extra in FIELD_SCHEMA:
        field_id = f"{file_}.{key}"
        if type_ == "checkbox":
            config[file_][key] = _coerce(type_, request.form.get(field_id))
        elif type_ in ("text", "password", "select"):
            # blank is a valid value here (e.g. clearing a password), unlike
            # number/float where an empty string can't be coerced at all.
            if field_id in request.form:
                config[file_][key] = _coerce(type_, request.form.get(field_id))
        elif field_id in request.form and request.form.get(field_id) != "":
            config[file_][key] = _coerce(type_, request.form.get(field_id))

    sessions = []
    for code in ("P", "Q", "R"):
        if request.form.get(f"session.{code}.enabled"):
            session_obj = {"sessionType": code}
            for f in SESSION_FIELDS:
                session_obj[f] = int(request.form.get(f"session.{code}.{f}", 0))
            sessions.append(session_obj)
    if not any(s["sessionType"] in ("P", "Q") for s in sessions):
        # server requires at least one non-race session
        sessions.insert(0, {"sessionType": "P", "sessionDurationMinutes": 10,
                            "hourOfDay": 10, "dayOfWeekend": 1, "timeMultiplier": 1})
    config["event"]["sessions"] = sessions

    cfg.save_all(config)
    return redirect(url_for("index"))


@app.route("/control/<action>", methods=["POST"])
@login_required
def control(action):
    if action == "start":
        proc.start()
    elif action == "stop":
        proc.stop()
    elif action == "restart":
        proc.restart()
    return redirect(url_for("index"))


@app.route("/api/status")
@login_required
def api_status():
    return jsonify(proc.status())


@app.route("/api/log")
@login_required
def api_log():
    return jsonify({"log": proc.tail_log()})


if __name__ == "__main__":
    cfg.ensure_defaults()
    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)
