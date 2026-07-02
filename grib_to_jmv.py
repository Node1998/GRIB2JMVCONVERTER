



from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

# xarray / cfgrib are imported lazily inside the functions that need them so
# this module can be imported (and the JMV writer unit-tested) on a machine
# without eccodes installed.


# --------------------------------------------------------------------------- #
# Parameter specifications (FNMOC conventions -- preserved from the original)  #
# --------------------------------------------------------------------------- #
@dataclass
class ParamSpec:
    """One output product. ``grib_tag`` is the eccodes shortName used to pull
    the variable out of the GRIB2 file."""
    grib_tag: str
    product_title: str
    grib_parameter_id: int
    units_code: int
    sort_level: int = 100
    process_id: int = 110
    data_type_code: int = 7
    grib_modifier_type: int = 1
    grib_modifier: float = 1.0
    data_multiplier: float = 0.1
    kelvin_to_celsius: bool = False
    missing_value: float = 0.0


PARAM_SPECS: dict[str, ParamSpec] = {
    "tmp":  ParamSpec("2t",   "2 METRE TEMPERATURE",        11, 11,  sort_level=100,
                      data_multiplier=0.1, kelvin_to_celsius=True),
    "gust": ParamSpec("gust", "WIND GUST",                 180, 180, sort_level=112,
                      data_multiplier=0.1),
    "msl":  ParamSpec("msl",  "MEAN SEA LEVEL PRESSURE",     1, 1,   sort_level=100,
                      data_multiplier=0.1),
    "10u":  ParamSpec("10u",  "10 METRE U WIND COMPONENT",  33, 33,  sort_level=100,
                      data_multiplier=0.1),
    "10v":  ParamSpec("10v",  "10 METRE V WIND COMPONENT",  34, 34,  sort_level=100,
                      data_multiplier=0.1),
    "mwd":  ParamSpec("mwd",  "MEAN WAVE DIRECTION",       107, 107, sort_level=100,
                      data_multiplier=0.1),
    "mwp":  ParamSpec("mwp",  "MEAN WAVE PERIOD",          108, 108, sort_level=100,
                      data_multiplier=0.1),
    "swh":  ParamSpec("swh",  "SIGNIFICANT WAVE HEIGHT",   100, 100, sort_level=100,
                      data_multiplier=0.01),
}


# --------------------------------------------------------------------------- #
# JMV header + writer (no eccodes required)                                   #
# --------------------------------------------------------------------------- #
HEADER_TERMINATOR = "END_OF_HEADER"


def _encode_header(header: dict) -> bytes:
    lines = [f"{k} = {v}" for k, v in header.items()]
    return ("\n".join(lines) + f"\n{HEADER_TERMINATOR}\n").encode("ascii")


def write_jmv(file_path: str, header: dict, data: np.ndarray,
              missing_value: float = 0.0) -> str:
    """Write a 2-D grid + ASCII header to a JMV file.

    The header's ``DATA_OFFSET`` is filled in with the real byte offset of the
    grid (two-pass: the placeholder and the final value are both 5-char
    zero-padded, so the header length is stable).
    """
    data = np.asarray(data, dtype=float)
    if data.ndim == 3:
        data = data.squeeze()
    if data.ndim != 2:
        raise ValueError(f"Data must be 2-D after squeeze, got shape {data.shape}")

    grib_modifier = float(header.get("GRIB_MODIFIER", 1.0)) or 1.0
    data_multiplier = float(header.get("DATA_MULTIPLIER", 1.0)) or 1.0

    # Replace NaNs before integer cast (prevents INT_MIN overflow artifacts).
    clean = np.nan_to_num(data, nan=float(missing_value))
    scaled = np.round((clean * grib_modifier) / data_multiplier)

    # Explicit little-endian int32 so output is byte-for-byte reproducible
    # regardless of host architecture.
    grid_bytes = scaled.astype("<i4").tobytes()

    header["NUMBER_OF_RECORDS"] = str(data.size)
    header["DATA_OFFSET"] = "00000"                      # placeholder, 5 chars
    header["DATA_OFFSET"] = str(len(_encode_header(header))).zfill(5)
    final_header = _encode_header(header)

    with open(file_path, "wb") as f:
        f.write(final_header)
        f.write(grid_bytes)
    return file_path


def build_header(spec: ParamSpec, da, grib_file_path: str) -> dict:
    """Assemble the JMV ASCII header for one parameter from its DataArray."""
    native = da.values.astype(float)
    if native.ndim > 2:
        native = native.squeeze()
    if spec.kelvin_to_celsius and np.nanmean(native) > 200:
        native = native - 273.15

    dtg = da.time.dt.strftime("%Y%m%d%H%M").item()
    tau = int(da.step.dt.total_seconds().item() // 3600) if "step" in da.coords else 0
    lat_n = int(da.sizes["latitude"])
    lon_n = int(da.sizes["longitude"])
    lat_spacing = abs(float(da.latitude[1] - da.latitude[0])) if lat_n > 1 else 0.25
    lon_spacing = abs(float(da.longitude[1] - da.longitude[0])) if lon_n > 1 else 0.25

    return {
        "VERSION": "1.0",
        "DATA_OFFSET": "0",
        "PLATFORM": "PC",
        "PRODUCT_TITLE": spec.product_title,
        "DATA_BASE_TITLE": spec.product_title,
        "CENTER_ID": "58",
        "PROCESS_ID": str(spec.process_id),
        "PRODUCT_TYPE": "GD",
        "UNKNOWN_PRODUCT_CODE": "0",
        "SORT_LEVEL": str(spec.sort_level),
        "DATA_TYPE_CODE": str(spec.data_type_code),
        "LABEL_CENTER_VALUE": "1",
        "GRIB_FILE_NAME": os.path.basename(grib_file_path),
        "GRIB_PARAMETER_ID": str(spec.grib_parameter_id),
        "GRIB_UNITS_CODE": "0",
        "UNITS_CODE": str(spec.units_code),
        "DATE_TIME_GROUP": dtg,
        "REQUESTED_TAU": str(tau),
        "DELIVERED_TAU": str(tau),
        "LEVEL_INDICATOR": "1",
        "LEVEL": "0.000000",
        "STANDARD_HEIGHT": "0.000000",
        "MB_LEVEL": "0.000000",
        "MODEL": "ECMWF",
        "BASE_LONGITUDE": f"{float(da.longitude.min()):.6f}",
        "BOTTOM_LATITUDE": f"{float(da.latitude.min()):.6f}",
        "PROJECTION": "1",
        "POLE_ON_SCREEN": "0",
        "LAT_POINTS": str(lat_n),
        "LON_POINTS": str(lon_n),
        "LABEL_LENGTH_CODE": "0",
        "HIGH_LOW_FLAG": "0",
        "TITLE_TYPE": "0",
        "DATA_MAX_VALUE": f"{np.nanmax(native):.1f}",
        "DATA_MIN_VALUE": f"{np.nanmin(native):.1f}",
        "ORIG_DATA_MAX_VALUE": f"{np.nanmax(native):.6f}",
        "ORIG_DATA_MIN_VALUE": f"{np.nanmin(native):.6f}",
        "CONTOUR_ORIGIN": "3",
        "CONTOUR_INTERVAL": "3",
        "CONTOUR_INTERVAL_COMPUTED": "NO",
        "CONTOUR_HIGH": "9999",
        "GRIB_MODIFIER_TYPE": str(spec.grib_modifier_type),
        "GRIB_MODIFIER": f"{spec.grib_modifier:.6f}",
        "DATA_MULTIPLIER": f"{spec.data_multiplier:.6f}",
        "LAND_SEA_FLAG": "1",
        "LATITUDE_GRID_SPACING": f"{lat_spacing:.6f}",
        "LONGITUDE_GRID_SPACING": f"{lon_spacing:.6f}",
        "PARTS_PER_RECORD": "1",
        "BYTES_PER_RECORD": "4",
        "RECORD_TYPE_PART1": "INTEGER",
        "BYTES_PER_POINT_PART1": "4",
    }, native


# --------------------------------------------------------------------------- #
# GRIB reading (requires eccodes / cfgrib)                                     #
# --------------------------------------------------------------------------- #
def _open_param(grib_file_path: str, short_name: str):
    """Open a single variable from a GRIB2 file by shortName, or return None."""
    import xarray as xr
    try:
        ds = xr.open_dataset(
            grib_file_path,
            engine="cfgrib",
            backend_kwargs={
                "filter_by_keys": {"shortName": short_name},
                "indexpath": "",
            },
        )
    except Exception:
        return None
    var_names = list(ds.data_vars)
    if not var_names:
        ds.close()
        return None
    return ds, ds[var_names[0]]


def detect_parameters(grib_file_path: str) -> list[dict]:
    """Return the subset of PARAM_SPECS actually present in ``grib_file_path``."""
    found = []
    for key, spec in PARAM_SPECS.items():
        opened = _open_param(grib_file_path, spec.grib_tag)
        if opened is not None:
            opened[0].close()
            found.append({"key": key, "title": spec.product_title})
    return found


def _jmv_filename(spec: ParamSpec, da, lon_n: int, lat_n: int) -> str:
    dtg = da.time.dt.strftime("%Y%m%d%H%M").item()
    tau = int(da.step.dt.total_seconds().item() // 3600) if "step" in da.coords else 0
    safe = spec.product_title.replace(" ", "_")
    return f"{safe}^GD^NCEP_GFS_{lon_n}X{lat_n}^{dtg}^0^{tau}.JMV"


def convert_grib_to_jmv(grib_file_path: str, output_dir: str,
                        param_specs: dict[str, ParamSpec] | None = None,
                        progress=None) -> list[str]:
    """Convert every parameter found in ``grib_file_path`` to a JMV file.

    Returns the list of written file paths. ``progress`` is an optional
    callable ``(stage: str, done: int, total: int)`` for UI updates.
    """
    specs = param_specs or PARAM_SPECS
    os.makedirs(output_dir, exist_ok=True)
    written: list[str] = []
    items = list(specs.items())

    for i, (key, spec) in enumerate(items):
        if progress:
            progress(spec.product_title, i, len(items))
        opened = _open_param(grib_file_path, spec.grib_tag)
        if opened is None:
            continue
        ds, da = opened
        try:
            header, native = build_header(spec, da, grib_file_path)
            lat_n, lon_n = int(da.sizes["latitude"]), int(da.sizes["longitude"])
            fname = _jmv_filename(spec, da, lon_n, lat_n)
            out_path = os.path.join(output_dir, fname)
            write_jmv(out_path, header, native, missing_value=spec.missing_value)
            written.append(out_path)
        except Exception as exc:  # one bad parameter shouldn't kill the batch
            print(f"  [!] {spec.grib_tag}: {exc}")
        finally:
            ds.close()

    if progress:
        progress("done", len(items), len(items))
    return written


def preview_grid(grib_file_path: str, param_key: str, max_dim: int = 180) -> dict:
    """Downsample one parameter to a small 2-D array for the UI heatmap.

    Returns ``{values, nx, ny, vmin, vmax, title}`` (values row-major, north-up).
    """
    spec = PARAM_SPECS[param_key]
    opened = _open_param(grib_file_path, spec.grib_tag)
    if opened is None:
        raise ValueError(f"{spec.product_title} not present in file")
    ds, da = opened
    try:
        arr = da.values.astype(float)
        if arr.ndim > 2:
            arr = arr.squeeze()
        if spec.kelvin_to_celsius and np.nanmean(arr) > 200:
            arr = arr - 273.15
        # north-up: GRIB latitudes usually descend (90 -> -90); flip if ascending
        if float(da.latitude[0]) < float(da.latitude[-1]):
            arr = arr[::-1, :]
        ny, nx = arr.shape
        sy = max(1, ny // max_dim)
        sx = max(1, nx // max_dim)
        small = arr[::sy, ::sx]
        finite = small[np.isfinite(small)]
        vmin = float(np.percentile(finite, 2)) if finite.size else 0.0
        vmax = float(np.percentile(finite, 98)) if finite.size else 1.0
        return {
            "values": np.nan_to_num(small, nan=vmin).round(3).flatten().tolist(),
            "nx": int(small.shape[1]),
            "ny": int(small.shape[0]),
            "vmin": vmin,
            "vmax": vmax,
            "title": spec.product_title,
        }
    finally:
        ds.close()
