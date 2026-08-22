"""Read/write helpers for ACC dedicated server JSON config files.

ACC requires every cfg/*.json file to be UTF-16LE with a BOM - plain UTF-8
is silently misread (or ignored) by the server. All I/O in this module
goes through write_json()/read_json() to guarantee that.
"""
import json
import os

CFG_DIR = os.environ.get("ACC_CFG_DIR", "/data/cfg")

CONFIGURATION_JSON = os.path.join(CFG_DIR, "configuration.json")
SETTINGS_JSON = os.path.join(CFG_DIR, "settings.json")
EVENT_JSON = os.path.join(CFG_DIR, "event.json")
EVENT_RULES_JSON = os.path.join(CFG_DIR, "eventRules.json")
ASSIST_RULES_JSON = os.path.join(CFG_DIR, "assistRules.json")
ENTRYLIST_JSON = os.path.join(CFG_DIR, "entrylist.json")

BOM = b"\xff\xfe"

# --- reference data (ACC Server Admin Handbook v1.10.2, appendix IX) -------

TRACKS = [
    "monza", "zolder", "brands_hatch", "silverstone", "paul_ricard", "misano",
    "spa", "nurburgring", "barcelona", "hungaroring", "zandvoort", "kyalami",
    "mount_panorama", "suzuka", "laguna_seca", "imola", "oulton_park",
    "donington", "snetterton", "cota", "indianapolis", "watkins_glen",
    "valencia", "nurburgring_24h",
]

CAR_GROUPS = ["FreeForAll", "GT3", "GT4", "GT2", "GTC", "TCX"]

SESSION_TYPES = {"P": "Practice", "Q": "Qualifying", "R": "Race"}

FORMATION_LAP_TYPES = {
    3: "Default (position control + UI)",
    0: "Old limiter lap",
    1: "Free (private servers only)",
}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    with open(path, "wb") as f:
        f.write(BOM + payload.encode("utf-16-le"))


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(BOM):
        text = raw[len(BOM):].decode("utf-16-le")
    else:
        # tolerate hand-edited / plain utf-8 files
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("utf-16-le")
    return json.loads(text) if text.strip() else default


# --- defaults ---------------------------------------------------------------
# The very first time a cfg file is generated (fresh /data volume), its
# defaults can be seeded from environment variables set in docker-compose.
# Every subsequent start ignores these env vars in favor of whatever is
# already on disk (i.e. whatever the dashboard last saved).

def _env(name, default, cast=str):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if cast is bool:
        return 1 if raw.lower() in ("1", "true", "yes", "on") else 0
    return cast(raw)


def default_configuration():
    return {
        "udpPort": _env("UDP_PORT", 9231, int),
        "tcpPort": _env("TCP_PORT", 9231, int),
        "maxConnections": _env("MAX_CONNECTIONS", 30, int),
        "lanDiscovery": 1,
        "registerToLobby": _env("REGISTER_TO_LOBBY", 1, bool),
        "configVersion": 1,
    }


def default_settings():
    return {
        "serverName": _env("SERVER_NAME", "My ACC Server"),
        "adminPassword": _env("ADMIN_PASSWORD", "changeme_admin"),
        "carGroup": _env("CAR_GROUP", "FreeForAll"),
        "trackMedalsRequirement": 0,
        "safetyRatingRequirement": -1,
        "racecraftRatingRequirement": -1,
        "password": _env("SERVER_PASSWORD", ""),
        "spectatorPassword": _env("SPECTATOR_PASSWORD", ""),
        "maxCarSlots": _env("MAX_CAR_SLOTS", 26, int),
        "dumpLeaderboards": 0,
        "isRaceLocked": 0,
        "randomizeTrackWhenEmpty": 0,
        "centralEntryListPath": "",
        "allowAutoDQ": 1,
        "shortFormationLap": 1,
        "dumpEntryList": 0,
        "formationLapType": 3,
        "configVersion": 1,
    }


def default_event():
    return {
        "track": _env("TRACK", "monza"),
        "preRaceWaitingTimeSeconds": 60,
        "sessionOverTimeSeconds": 120,
        "ambientTemp": _env("AMBIENT_TEMP", 22, int),
        "cloudLevel": _env("CLOUD_LEVEL", 0.3, float),
        "rain": _env("RAIN", 0.0, float),
        "weatherRandomness": _env("WEATHER_RANDOMNESS", 1, int),
        "postRaceSeconds": 60,
        "configVersion": 1,
        "sessions": [
            {"hourOfDay": 10, "dayOfWeekend": 1, "timeMultiplier": 1,
             "sessionType": "P", "sessionDurationMinutes": 20},
            {"hourOfDay": 14, "dayOfWeekend": 2, "timeMultiplier": 4,
             "sessionType": "Q", "sessionDurationMinutes": 15},
            {"hourOfDay": 15, "dayOfWeekend": 3, "timeMultiplier": 2,
             "sessionType": "R", "sessionDurationMinutes": 20},
        ],
    }


def default_event_rules():
    return {
        "qualifyStandingType": 1,
        "pitWindowLengthSec": -1,
        "driverStintTimeSec": -1,
        "mandatoryPitstopCount": 0,
        "maxTotalDrivingTime": -1,
        "maxDriversCount": 1,
        "isRefuellingAllowedInRace": True,
        "isRefuellingTimeFixed": False,
        "isMandatoryPitstopRefuellingRequired": False,
        "isMandatoryPitstopTyreChangeRequired": False,
        "isMandatoryPitstopSwapDriverRequired": False,
        "tyreSetCount": 50,
    }


def default_assist_rules():
    return {
        "stabilityControlLevelMax": 100,
        "disableAutosteer": 0,
        "disableAutoLights": 0,
        "disableAutoWiper": 0,
        "disableAutoEngineStart": 0,
        "disableAutoPitLimiter": 0,
        "disableAutoGear": 0,
        "disableAutoClutch": 0,
        "disableIdealLine": 0,
    }


def default_entrylist():
    return {"entries": [], "forceEntryList": 0}


DEFAULTS = {
    CONFIGURATION_JSON: default_configuration,
    SETTINGS_JSON: default_settings,
    EVENT_JSON: default_event,
    EVENT_RULES_JSON: default_event_rules,
    ASSIST_RULES_JSON: default_assist_rules,
    ENTRYLIST_JSON: default_entrylist,
}


def ensure_defaults():
    """Write any missing cfg file with its default content. Never overwrites
    an existing file - this is what makes the dashboard's edits (and any
    hand edits to entrylist.json) survive a container restart."""
    os.makedirs(CFG_DIR, exist_ok=True)
    for path, factory in DEFAULTS.items():
        if not os.path.exists(path):
            write_json(path, factory())


def load_all():
    return {
        "configuration": read_json(CONFIGURATION_JSON, default_configuration()),
        "settings": read_json(SETTINGS_JSON, default_settings()),
        "event": read_json(EVENT_JSON, default_event()),
        "eventRules": read_json(EVENT_RULES_JSON, default_event_rules()),
        "assistRules": read_json(ASSIST_RULES_JSON, default_assist_rules()),
    }


def save_all(cfg):
    write_json(CONFIGURATION_JSON, cfg["configuration"])
    write_json(SETTINGS_JSON, cfg["settings"])
    write_json(EVENT_JSON, cfg["event"])
    write_json(EVENT_RULES_JSON, cfg["eventRules"])
    write_json(ASSIST_RULES_JSON, cfg["assistRules"])
