from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from flask import (Flask, jsonify, render_template, request,
                   send_file, abort)
from werkzeug.utils import secure_filename
import grib_to_jmv as g2j

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
OUTPUT = os.path.join(BASE, "output")

# Ensure base directories exist
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # Aligned with Render's 100MB proxy limit

def _eccodes_ready() -> bool:
    try:
        import cfgrib  # noqa: F401
        return True
    except Exception:
        return False

@app.route("/")
def index():
    return render_template("index.html", eccodes=_eccodes_ready())

@app.route("/api/upload", methods=["POST"])
def upload():
    """Receive GRIB2 files, store them, and report detected parameters."""
    token = uuid.uuid4().hex[:12]
    sess_dir = os.path.join(UPLOADS, token)
    os.makedirs(sess_dir, exist_ok=True)

    # Resilient search: checks 'files', 'file', or fallback to any file attached in the request
    incoming = (
        request.files.getlist("files") or 
        request.files.getlist("file") or 
        list(request.files.values())
    )

    if not incoming:
        return jsonify(error="No files received"), 400

    files_info = []
    for fs in incoming:
        if not fs or fs.filename == '':
            continue
        name = secure_filename(fs.filename) or "grib.bin"
        path = os.path.join(sess_dir, name)
        fs.save(path)

        params, err = [], None
        if _eccodes_ready():
            try:
                params = g2j.detect_parameters(path)
            except Exception as exc:
                err = str(exc)

        files_info.append({
            "name": name,
            "size": os.path.getsize(path),
            "params": params,
            "error": err,
        })

    return jsonify(token=token, files=files_info, eccodes=_eccodes_ready())

@app.route("/api/convert", methods=["POST"])
def convert():
    """Convert every uploaded file in the session to JMV and package them."""
    if not _eccodes_ready():
        return jsonify(error="eccodes/cfgrib not installed on the server. "
                             "Install it to run conversions."), 503

    token = (request.json or {}).get("token")
    sess_dir = os.path.join(UPLOADS, str(token))
    
    # Stateless check: check if the session folder exists on disk
    if not token or not os.path.isdir(sess_dir):
        return jsonify(error="Unknown session token or upload expired"), 404

    jmv_dir = os.path.join(OUTPUT, f"{token}_jmv")
    if os.path.exists(jmv_dir):
        shutil.rmtree(jmv_dir)
    os.makedirs(jmv_dir, exist_ok=True)

    # Read uploaded files directly from disk
    uploaded_files = [f for f in os.listdir(sess_dir) if os.path.isfile(os.path.join(sess_dir, f))]

    total, results = 0, []
    for name in uploaded_files:
        src = os.path.join(sess_dir, name)
        try:
            written = g2j.convert_grib_to_jmv(src, jmv_dir)
            total += len(written)
            results.append({"file": name, "written": len(written)})
        except Exception as exc:
            results.append({"file": name, "written": 0, "error": str(exc)})

    return jsonify(token=token, total=total, results=results)

@app.route("/api/preview")
def preview():
    """Downsampled grid for the heatmap. ?token=&file=&param="""
    if not _eccodes_ready():
        return jsonify(error="eccodes not installed"), 503

    token = request.args.get("token")
    fname = request.args.get("file")
    param = request.args.get("param")
    
    sess_dir = os.path.join(UPLOADS, str(token))
    if not token or not os.path.isdir(sess_dir):
        return jsonify(error="Unknown session"), 404

    src = os.path.join(sess_dir, secure_filename(fname or ""))
    if not os.path.exists(src):
        return jsonify(error="File not found"), 404

    try:
        return jsonify(g2j.preview_grid(src, param))
    except Exception as exc:
        return jsonify(error=str(exc)), 400

@app.route("/api/download/<token>")
def download(token):
    """Zip the session's JMV output and stream it."""
    sess_dir = os.path.join(UPLOADS, str(token))
    jmv_dir = os.path.join(OUTPUT, f"{token}_jmv")
    
    if not os.path.isdir(sess_dir) or not os.path.isdir(jmv_dir):
        abort(404)

    zip_path = os.path.join(OUTPUT, f"JMV_Package_{token}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(jmv_dir):
            for f in files:
                full = os.path.join(root, f)
                zf.write(full, arcname=os.path.relpath(full, jmv_dir))

    return send_file(zip_path, as_attachment=True,
                     download_name=os.path.basename(zip_path))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
