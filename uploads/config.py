"""config.py — all runtime config from env vars (12-factor). No secrets in code."""
import os

DATA_DIR      = os.environ.get("JMV_DATA_DIR", "/data/jmv")   # persistent disk
TMP_DIR       = os.environ.get("JMV_TMP_DIR", "/tmp")
MODEL_TYPE    = os.environ.get("ECMWF_MODEL", "HRES")
RESOLUTION    = os.environ.get("ECMWF_RES", "0.25/0.25")
MAX_FCST_HR   = int(os.environ.get("MAX_FCST_HR", "72"))
STEP_INTERVAL = int(os.environ.get("STEP_INTERVAL", "6"))
RETENTION_HRS = int(os.environ.get("RETENTION_HRS", "48"))    # prune older cycles
CRON_SECRET   = os.environ.get("CRON_SECRET", "")             # gate ingest route
PORT          = int(os.environ.get("PORT", "8000"))

# Model -> open-data backend + parameter set. NOTE: default Client() serves
# IFS, so AIFS MUST use client_model='aifs-single' or it silently pulls IFS.
MODEL_CONFIGS = {
    "HRES":     {"stream": "oper", "type": "fc", "client_model": "ifs",
                 "parameters": ["2t", "10u", "10v", "msl", "gust"],
                 "valid_cycles": ["00", "06", "12", "18"]},
    "AIFS":     {"stream": "oper", "type": "fc", "client_model": "aifs-single",
                 "parameters": ["2t", "10u", "10v", "msl"],
                 "valid_cycles": ["00", "06", "12", "18"]},
    "ENSEMBLE": {"stream": "enfo", "type": "cf", "client_model": "ifs",
                 "parameters": ["2t", "10u", "10v", "msl", "gust", "swh"],
                 "valid_cycles": ["00", "06", "12", "18"]},
    "WAVE":     {"stream": "wave", "type": "fc", "client_model": "ifs",
                 "parameters": ["swh", "mwd", "mwp"],
                 "valid_cycles": ["00", "12"]},
}
