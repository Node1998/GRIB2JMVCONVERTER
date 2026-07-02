# wsgi.py — repo root. Render start command: gunicorn wsgi:app
import os
import sys

# app.py lives in grib2jmv/, one level below this file
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "grib2jmv"))

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run()
