/* GRIB2 -> JMV  ·  client logic (vanilla, offline) */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { token: null, files: [], activeFile: null, activeParam: null };

  /* ---- engine status ---------------------------------------------- */
  (function engine() {
    const ready = document.body.dataset.eccodes === "ready";
    const el = $("engineStatus");
    el.classList.add(ready ? "ready" : "offline");
    el.querySelector(".status-text").textContent = ready ? "engine ready" : "engine offline";
  })();

  /* ---- drag + drop ------------------------------------------------- */
  const dz = $("dropzone"), input = $("fileInput");
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));
  input.addEventListener("change", () => handleFiles(input.files));

  function fmtSize(b) {
    if (b > 1e9) return (b / 1e9).toFixed(2) + " GB";
    if (b > 1e6) return (b / 1e6).toFixed(1) + " MB";
    if (b > 1e3) return (b / 1e3).toFixed(0) + " KB";
    return b + " B";
  }

  async function handleFiles(fileList) {
    const files = [...fileList];
    if (!files.length) return;
    setProgress("Scanning " + files.length + " file(s)…", 0.15, false);

    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    let data;
    try {
      data = await (await fetch("/api/upload", { method: "POST", body: fd })).json();
    } catch (err) {
      setProgress("Upload failed — is the server running?", 0, false);
      return;
    }
    if (data.error) { setProgress(data.error, 0, false); return; }

    state.token = data.token;
    state.files = data.files;

    // file list
    const fl = $("filelist");
    fl.hidden = false;
    fl.innerHTML = data.files
      .map((f) => `<li><span>${f.name}</span><span class="fsize">${fmtSize(f.size)}</span></li>`)
      .join("");

    renderDetected(data.files, data.eccodes);
    $("convertBtn").disabled = !data.eccodes;
    setProgress(data.eccodes
      ? `${data.files.length} file(s) ready — batch convert when set.`
      : "Files staged. Install eccodes on the server to convert.", 0.25, false);
  }

  function renderDetected(files, eccodes) {
    const rows = $("paramRows"), count = $("paramCount");
    if (!eccodes) {
      rows.innerHTML = `<li class="param-empty">Engine offline — parameters can’t be scanned.</li>`;
      count.textContent = "—";
      return;
    }
    // union of params across all files
    const seen = new Map();
    files.forEach((f) => (f.params || []).forEach((p) => seen.set(p.key, p.title)));
    if (!seen.size) {
      rows.innerHTML = `<li class="param-empty">No known parameters found in these files.</li>`;
      count.textContent = "0";
      return;
    }
    count.textContent = seen.size;
    rows.innerHTML = [...seen.values()]
      .map((title) => `<li><span class="check">✓</span>${title}</li>`)
      .join("");
  }

  /* ---- batch convert ---------------------------------------------- */
  $("convertBtn").addEventListener("click", async () => {
    if (!state.token) return;
    const btn = $("convertBtn");
    btn.disabled = true;
    btn.classList.add("busy");
    btn.querySelector(".btn-label").textContent = "Converting…";
    setProgress("Reading GRIB2 grids…", 0.45, false);

    let data;
    try {
      data = await (await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: state.token }),
      })).json();
    } catch {
      setProgress("Conversion request failed.", 0, false);
      btn.disabled = false; btn.classList.remove("busy");
      btn.querySelector(".btn-label").textContent = "Batch convert";
      return;
    }

    btn.classList.remove("busy");
    btn.querySelector(".btn-label").textContent = "Batch convert";
    btn.disabled = false;

    if (data.error) { setProgress(data.error, 0, false); return; }

    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    setProgress(`${stamp}_JMV — ${data.total} grid(s) written.`, 1, true);
    $("exportBtn").disabled = data.total === 0;
    $("shareBtn").disabled = data.total === 0;

    buildChips();
  });

  /* ---- parameter chips + preview ---------------------------------- */
  function buildChips() {
    const chips = $("chips");
    // first file that actually has params
    const file = state.files.find((f) => (f.params || []).length);
    if (!file) return;
    state.activeFile = file.name;
    chips.innerHTML = file.params
      .map((p) => `<button class="chip" data-key="${p.key}">${p.title}</button>`)
      .join("");
    chips.querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => selectParam(c.dataset.key, c)));
    // auto-preview the first parameter
    const first = chips.querySelector(".chip");
    if (first) selectParam(first.dataset.key, first);
  }

  async function selectParam(key, chipEl) {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chipEl.classList.add("active");
    state.activeParam = key;
    $("vizMeta").textContent = "loading…";
    try {
      const q = new URLSearchParams({ token: state.token, file: state.activeFile, param: key });
      const grid = await (await fetch("/api/preview?" + q)).json();
      if (grid.error) { $("vizMeta").textContent = grid.error; return; }
      drawHeatmap(grid);
    } catch {
      $("vizMeta").textContent = "preview unavailable";
    }
  }

  /* ---- heatmap ----------------------------------------------------- */
  const STOPS = [
    [0.00, [11, 31, 36]],
    [0.40, [14, 124, 123]],
    [0.72, [79, 209, 197]],
    [1.00, [242, 181, 68]],
  ];
  function ramp(t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < STOPS.length; i++) {
      if (t <= STOPS[i][0]) {
        const [t0, c0] = STOPS[i - 1], [t1, c1] = STOPS[i];
        const f = (t - t0) / (t1 - t0 || 1);
        return [0, 1, 2].map((j) => Math.round(c0[1][j] + (c1[1][j] - c0[1][j]) * f));
      }
    }
    return STOPS[STOPS.length - 1][1];
  }

  function drawHeatmap(grid) {
    const { values, nx, ny, vmin, vmax, title } = grid;
    $("vizIdle").style.display = "none";
    $("vizMeta").textContent = `${title} · ${nx}×${ny}`;

    // render at native grid resolution, then scale up for a soft field
    const off = document.createElement("canvas");
    off.width = nx; off.height = ny;
    const octx = off.getContext("2d");
    const img = octx.createImageData(nx, ny);
    const span = (vmax - vmin) || 1;
    for (let i = 0; i < values.length; i++) {
      const [r, g, b] = ramp((values[i] - vmin) / span);
      img.data[i * 4] = r; img.data[i * 4 + 1] = g;
      img.data[i * 4 + 2] = b; img.data[i * 4 + 3] = 255;
    }
    octx.putImageData(img, 0, 0);

    const cv = $("vizCanvas");
    const ctx = cv.getContext("2d");
    cv.height = Math.round(cv.width * (ny / nx));
    ctx.imageSmoothingEnabled = true;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.drawImage(off, 0, 0, cv.width, cv.height);

    // faint graticule overlay (echoes a chart grid without coastlines)
    ctx.strokeStyle = "rgba(231,238,245,0.06)";
    ctx.lineWidth = 1;
    for (let gx = 1; gx < 12; gx++) {
      const x = (gx / 12) * cv.width;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, cv.height); ctx.stroke();
    }
    for (let gy = 1; gy < 7; gy++) {
      const y = (gy / 7) * cv.height;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cv.width, y); ctx.stroke();
    }

    const cb = $("colorbar");
    cb.hidden = false;
    cb.querySelector(".cb-min").textContent = vmin.toFixed(1);
    cb.querySelector(".cb-max").textContent = vmax.toFixed(1);
  }

  /* ---- export + share --------------------------------------------- */
  $("exportBtn").addEventListener("click", () => {
    if (state.token) window.location = "/api/download/" + state.token;
  });
  $("shareBtn").addEventListener("click", () => {
    setProgress("Package ready in /output — wire Share to Outlook/SharePoint here.", 1, true);
  });

  /* ---- progress strip --------------------------------------------- */
  function setProgress(label, frac, done) {
    const l = $("progLabel"), f = $("progFill");
    l.textContent = label;
    l.classList.toggle("done", !!done);
    f.style.width = Math.round(frac * 100) + "%";
    f.classList.toggle("done", !!done);
  }
})();
