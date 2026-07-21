"""converter.py — GRIB2 -> JMV core logic (extracted from GRIB2JMV_GUIDE).

No Colab / no eccodes required to import; cfgrib is imported lazily so the
JMV writer stays unit-testable on hosts without the native lib.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Parameter specifications (FNMOC conventions -- preserved from the notebook)  #
# --------------------------------------------------------------------------- #
@dataclass
class ParamSpec:
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
    "tmp":  ParamSpec("2t",   "2 METRE TEMPERATURE",        11, 11,  data_multiplier=0.1,
                      kelvin_to_celsius=True),
    "gust": ParamSpec("gust", "WIND GUST",                 180, 180, sort_level=112,
                      data_multiplier=0.1),
    "msl":  ParamSpec("msl",  "MEAN SEA LEVEL PRESSURE",     1, 1,   data_multiplier=0.1),
    "10u":  ParamSpec("10u",  "10 METRE U WIND COMPONENT",  33, 33,  data_multiplier=0.1),
    "10v":  ParamSpec("10v",  "10 METRE V WIND COMPONENT",  34, 34,  data_multiplier=0.1),
    "mwd":  ParamSpec("mwd",  "MEAN WAVE DIRECTION",       107, 107, data_multiplier=0.1),
    "mwp":  ParamSpec("mwp",  "MEAN WAVE PERIOD",          108, 108, data_multiplier=0.1),
    "swh":  ParamSpec("swh",  "SIGNIFICANT WAVE HEIGHT",   100, 100, data_multiplier=0.01),
}

SPECS_BY_TAG: dict[str, ParamSpec] = {s.grib_tag: s for s in PARAM_SPECS.values()}


# --------------------------------------------------------------------------- #
# JMV header + writer (no eccodes required)                                   #
# --------------------------------------------------------------------------- #
HEADER_TERMINATOR = "END_OF_HEADER"


def _encode_header(header: dict) -> bytes:
    lines = [f"{k} = {v}" for k, v in header.items()]
    return ("\n".join(lines) + f"\n{HEADER_TERMINATOR}\n").encode("ascii")


def write_jmv(file_path: str, header: dict, data: np.ndarray,
              missing_value: float = 0.0) -> str:
    """Write a 2-D grid + ASCII header. DATA_OFFSET is 5-char zero-padded so
    the two-pass header length stays stable."""
    data = np.asarray(data, dtype=float)
    if data.ndim == 3:
        data = data.squeeze()
    if data.ndim != 2:
        raise ValueError(f"Data must be 2-D after squeeze, got shape {data.shape}")

    grib_modifier = float(header.get("GRIB_MODIFIER", 1.0)) or 1.0
    data_multiplier = float(header.get("DATA_MULTIPLIER", 1.0)) or 1.0

    # NaN scrub before int cast prevents INT_MIN overflow artifacts.
    clean = np.nan_to_num(data, nan=float(missing_value))
    scaled = np.round((clean * grib_modifier) / data_multiplier)

    # Explicit little-endian int32 -> byte-for-byte reproducible across hosts.
    grid_bytes = scaled.astype("<i4").tobytes()

    header["NUMBER_OF_RECORDS"] = str(data.size)
    header["DATA_OFFSET"] = "00000"
    header["DATA_OFFSET"] = str(len(_encode_header(header))).zfill(5)
    final_header = _encode_header(header)

    with open(file_path, "wb") as f:
        f.write(final_header)
        f.write(grid_bytes)
    return file_path


def _dtg_and_tau(da) -> tuple[str, int]:
    """Run DTG (YYYYMMDDHHMM) + tau (hours). Robust to scalar coords and to
    0-d slices from .isel(step=i)."""
    dtg = pd.Timestamp(np.asarray(da.time.values).item()).strftime("%Y%m%d%H%M")
    if "step" in da.coords:
        tau = int(pd.Timedelta(np.asarray(da.step.values).item()).total_seconds() // 3600)
    else:
        tau = 0
    return dtg, tau


def build_header(spec: ParamSpec, da, grib_file_path: str,
                 model_tag: str = "ECMWF") -> tuple[dict, np.ndarray]:
    native = da.values.astype(float)
    if native.ndim > 2:
        native = native.squeeze()
    # K->C only when values are plausibly Kelvin (mean > 200).
    if spec.kelvin_to_celsius and np.nanmean(native) > 200:
        native = native - 273.15

    dtg, tau = _dtg_and_tau(da)
    lat_n = int(da.sizes["latitude"])
    lon_n = int(da.sizes["longitude"])
    lat_spacing = abs(float(da.latitude[1] - da.latitude[0])) if lat_n > 1 else 0.25
    lon_spacing = abs(float(da.longitude[1] - da.longitude[0])) if lon_n > 1 else 0.25

    return {
        "VERSION": "1.0", "DATA_OFFSET": "0", "PLATFORM": "PC",
        "PRODUCT_TITLE": spec.product_title, "DATA_BASE_TITLE": spec.product_title,
        "CENTER_ID": "58", "PROCESS_ID": str(spec.process_id), "PRODUCT_TYPE": "GD",
        "UNKNOWN_PRODUCT_CODE": "0", "SORT_LEVEL": str(spec.sort_level),
        "DATA_TYPE_CODE": str(spec.data_type_code), "LABEL_CENTER_VALUE": "1",
        "GRIB_FILE_NAME": os.path.basename(grib_file_path),
        "GRIB_PARAMETER_ID": str(spec.grib_parameter_id), "GRIB_UNITS_CODE": "0",
        "UNITS_CODE": str(spec.units_code), "DATE_TIME_GROUP": dtg,
        "REQUESTED_TAU": str(tau), "DELIVERED_TAU": str(tau),
        "LEVEL_INDICATOR": "1", "LEVEL": "0.000000", "STANDARD_HEIGHT": "0.000000",
        "MB_LEVEL": "0.000000", "MODEL": model_tag,
        "BASE_LONGITUDE": f"{float(da.longitude.min()):.6f}",
        "BOTTOM_LATITUDE": f"{float(da.latitude.min()):.6f}",
        "PROJECTION": "1", "POLE_ON_SCREEN": "0",
        "LAT_POINTS": str(lat_n), "LON_POINTS": str(lon_n),
        "LABEL_LENGTH_CODE": "0", "HIGH_LOW_FLAG": "0", "TITLE_TYPE": "0",
        "DATA_MAX_VALUE": f"{np.nanmax(native):.1f}",
        "DATA_MIN_VALUE": f"{np.nanmin(native):.1f}",
        "ORIG_DATA_MAX_VALUE": f"{np.nanmax(native):.6f}",
        "ORIG_DATA_MIN_VALUE": f"{np.nanmin(native):.6f}",
        "CONTOUR_ORIGIN": "3", "CONTOUR_INTERVAL": "3",
        "CONTOUR_INTERVAL_COMPUTED": "NO", "CONTOUR_HIGH": "9999",
        "GRIB_MODIFIER_TYPE": str(spec.grib_modifier_type),
        "GRIB_MODIFIER": f"{spec.grib_modifier:.6f}",
        "DATA_MULTIPLIER": f"{spec.data_multiplier:.6f}",
        "LAND_SEA_FLAG": "1",
        "LATITUDE_GRID_SPACING": f"{lat_spacing:.6f}",
        "LONGITUDE_GRID_SPACING": f"{lon_spacing:.6f}",
        "PARTS_PER_RECORD": "1", "BYTES_PER_RECORD": "4",
        "RECORD_TYPE_PART1": "INTEGER", "BYTES_PER_POINT_PART1": "4",
    }, native


def _jmv_filename(spec: ParamSpec, da, lon_n: int, lat_n: int,
                  model_tag: str = "ECMWF") -> str:
    dtg, tau = _dtg_and_tau(da)
    safe = spec.product_title.replace(" ", "_")
    return f"{safe}^GD^{model_tag}_{lon_n}X{lat_n}^{dtg}^0^{tau}.JMV"


# --------------------------------------------------------------------------- #
# GRIB reading (requires eccodes / cfgrib)                                     #
# --------------------------------------------------------------------------- #
def _open_param(grib_file_path: str, short_name: str):
    import xarray as xr
    try:
        ds = xr.open_dataset(
            grib_file_path, engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"shortName": short_name},
                            "indexpath": ""},
        )
    except Exception:
        return None
    var_names = list(ds.data_vars)
    if not var_names:
        ds.close()
        return None
    return ds, ds[var_names[0]]


def _write_one(spec: ParamSpec, da2d, grib_name: str, output_dir: str,
               model_tag: str) -> str:
    header, native = build_header(spec, da2d, grib_name, model_tag=model_tag)
    lat_n, lon_n = int(da2d.sizes["latitude"]), int(da2d.sizes["longitude"])
    fname = _jmv_filename(spec, da2d, lon_n, lat_n, model_tag=model_tag)
    out_path = os.path.join(output_dir, fname)
    write_jmv(out_path, header, native, missing_value=spec.missing_value)
    return out_path


def convert_bundle_to_jmv(bundle_path: str, grib_tags: list[str],
                          output_dir: str, model_tag: str = "ECMWF") -> int:
    """Open each shortName once; write one JMV per forecast step. Returns count."""
    os.makedirs(output_dir, exist_ok=True)
    n_written = 0
    for tag in grib_tags:
        spec = SPECS_BY_TAG.get(tag)
        if spec is None:
            print(f"  [!] No ParamSpec for shortName '{tag}', skipping.")
            continue
        opened = _open_param(bundle_path, tag)
        if opened is None:
            print(f"  [!] '{tag}' not present in bundle.")
            continue
        ds, da = opened
        try:
            n_steps = da.sizes.get("step", 1)
            for s in range(n_steps):
                da2d = da.isel(step=s) if "step" in da.dims else da
                try:
                    _write_one(spec, da2d, bundle_path, output_dir, model_tag)
                    n_written += 1
                except Exception as exc:
                    print(f"  [!] {tag} step-index {s}: {exc}")
        finally:
            ds.close()
    return n_written
