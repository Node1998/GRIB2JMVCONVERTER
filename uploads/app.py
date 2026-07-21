"""app.py — Flask front end: health, cron trigger, and JMV file browsing."""
import hmac
import os
import logging
import threading

from flask import Flask, jsonify, request, send_from_directory, abort

import config
import ingest

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
os.makedirs(config.DATA_DIR, exist_ok=True)


def _authorized(req) -> bool:
    """Constant-time secret check. Without it, the expensive pull is
    world-triggerable (cost + rate-limit DoS)."""
    if not config.CRON_SECRET:
        return True  # dev only; SET CRON_SECRET in production
    return hmac.compare_digest(req.headers.get("X-Cron-Secret", ""),
                               config.CRON_SECRET)


@app.route("/health")
def health():
    return jsonify(status="up", model=config.MODEL_TYPE, last_run=ingest.status())


@app.route("/cron/ingest", methods=["POST"])
def cron_ingest():
    """Triggered every 6h by Render Cron via self-curl. Returns immediately;
    the pull runs in a background thread (Render request timeout ~30s)."""
    if not _authorized(request):
        abort(403)
    if not ingest.try_acquire():
        return jsonify(status="busy", detail="ingest already running"), 409
    threading.Thread(target=ingest.ingest_worker, daemon=True).start()
    return jsonify(status="accepted", detail="ingest started"), 202


@app.route("/files")
def list_files():
    out = {}
    for name in sorted(os.listdir(config.DATA_DIR), reverse=True):
        p = os.path.join(config.DATA_DIR, name)
        if os.path.isdir(p):
            out[name] = sorted(os.listdir(p))
    return jsonify(cycles=out)


@app.route("/files/<cycle>/<path:fname>")
def get_file(cycle, fname):
    # send_from_directory blocks path traversal; validate cycle dir exists.
    safe_dir = os.path.join(config.DATA_DIR, cycle)
    if not os.path.isdir(safe_dir):
        abort(404)
    return send_from_directory(safe_dir, fname, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
