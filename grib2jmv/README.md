# GRIB2 → JMV converter

Local web tool that batch-converts GRIB2 model output into FNMOC JMV
binary grid files, with a dark instrument-console UI and a live grid
preview. Refined from the original Colab pipeline.


## Try it here: https://grib2jmvconverter.onrender.com (We onnat render free tier so it takes a minute to load lmao)

## What changed from the notebook
- **Per-parameter GRIB filtering.** Each product is read by its own eccodes
  `shortName` (`2t`, `msl`, `10u`, `10v`, `swh`, `mwp`, `mwd`, `gust`) instead
  of always taking the first variable in the file — the notebook silently
  wrote duplicates.
- **Deterministic encoding.** Grids are written as explicit little-endian
  `int32` (`<i4`), so output is byte-identical across machines.
- **Verified header offset.** `DATA_OFFSET` is computed and unit-tested to land
  exactly on the first data byte.
- **Graceful batch.** A bad parameter logs and is skipped; the rest convert.
- **`detect_parameters()`** drives the "Parameters detected" panel.
- FNMOC parameter / units / process codes are preserved exactly from the specs.

## Run
```
pip install -r requirements.txt
python app.py        # or double-click run.bat on Windows
```
Open http://127.0.0.1:5000 , drop GRIB2 files, **Batch convert**, then
**Export package** for the zipped JMV set.

GRIB parsing needs eccodes. On Windows: `conda install -c conda-forge eccodes cfgrib`.
The server still starts without it (engine shows "offline") so the UI is
inspectable.

## Files
- `grib_to_jmv.py` — conversion core (importable, JMV writer is eccodes-free)
- `app.py` — Flask server / API
- `templates/index.html`, `static/style.css`, `static/app.js` — front end
