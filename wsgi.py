# wsgi.py — repo root entrypoint for gunicorn
# Render start command: gunicorn wsgi:app
import os, sys

# grib2jmv/ contains app.py and grib_to_jmv.py
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "grib2jmv"))

from app import app  # noqa: E402 — path must be set first

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
