"""ingest.py — pull one ECMWF cycle, convert to JMV, prune old output.

Thread-safe single-flight ingest with in-process status. Kept separate from
the Flask app so it can be invoked from a CLI (`python -m ingest`) or a test.
"""
import os
import logging
import threading
from datetime import datetime, timezone, timedelta

from ecmwf.opendata import Client

import config
from converter import convert_bundle_to_jmv, SPECS_BY_TAG

log = logging.getLogger("jmv-ingest")

# Single-flight guard: overlapping cron triggers must not double-pull a cycle.
_ingest_lock = threading.Lock()
_last_run = {"cycle": None, "started": None, "finished": None,
             "files": 0, "status": "idle"}


def status() -> dict:
    return dict(_last_run)


def try_acquire() -> bool:
    return _ingest_lock.acquire(blocking=False)


def _latest_available_cycle(cfg):
    """Newest run the rolling open-data window actually serves. ECMWF open
    data lags real time ~7-9h; probing avoids blind 404s on a just-started run."""
    client = Client(source="ecmwf", model=cfg["client_model"])
    run = client.latest(type=cfg["type"], stream=cfg["stream"])  # UTC datetime
    return client, run.strftime("%Y-%m-%d"), run.strftime("%H")


def _prune_old():
    """Delete cycle dirs older than RETENTION_HRS (persistent disk is finite)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.RETENTION_HRS)
    for name in os.listdir(config.DATA_DIR):
        path = os.path.join(config.DATA_DIR, name)
        if not os.path.isdir(path):
            continue
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
            if mtime < cutoff:
                for f in os.listdir(path):
                    os.remove(os.path.join(path, f))
                os.rmdir(path)
                log.info("Pruned old cycle: %s", name)
        except OSError:
            log.exception("Prune failed for %s", name)


def run_ingest() -> dict:
    """Pull latest available cycle, convert, prune. Idempotent per cycle."""
    cfg = config.MODEL_CONFIGS[config.MODEL_TYPE]
    os.makedirs(config.DATA_DIR, exist_ok=True)
    client, date_str, cycle = _latest_available_cycle(cfg)

    cycle_dir = os.path.join(config.DATA_DIR,
                             f"{date_str.replace('-', '')}_{cycle}z")
    if os.path.isdir(cycle_dir) and os.listdir(cycle_dir):
        log.info("Cycle %s %sz already ingested; skipping.", date_str, cycle)
        return {"skipped": True, "cycle": f"{date_str} {cycle}z", "files": 0}

    os.makedirs(cycle_dir, exist_ok=True)
    steps = sorted(set(range(0, config.MAX_FCST_HR + 1, config.STEP_INTERVAL)) | {0})
    tags = [t for t in cfg["parameters"] if t in SPECS_BY_TAG]

    # Group params by step list (gust lacks analysis step 0) -> bundled retrieves.
    groups: dict[tuple, list[str]] = {}
    for tag in tags:
        key = tuple(s for s in steps if s != 0) if tag == "gust" else tuple(steps)
        groups.setdefault(key, []).append(tag)

    total = 0
    for grp_steps, grp_tags in groups.items():
        bundle = os.path.join(
            config.TMP_DIR,
            f"{config.MODEL_TYPE}_{date_str}_{cycle}_{'-'.join(grp_tags)}.grib2")
        try:
            client.retrieve(date=date_str, time=cycle, type=cfg["type"],
                            step=list(grp_steps), param=grp_tags,
                            stream=cfg["stream"], grid=config.RESOLUTION,
                            target=bundle)
            n = convert_bundle_to_jmv(bundle, grp_tags, cycle_dir,
                                      model_tag=config.MODEL_TYPE)
            total += n
            log.info("Converted %d JMV for %s", n, grp_tags)
        except Exception:
            log.exception("Bundle failed for %s", grp_tags)
        finally:
            if os.path.exists(bundle):
                os.remove(bundle)

    _prune_old()
    return {"skipped": False, "cycle": f"{date_str} {cycle}z",
            "files": total, "dir": cycle_dir}


def ingest_worker():
    """Background entry point: updates status, always releases the lock."""
    _last_run.update(status="running",
                     started=datetime.now(timezone.utc).isoformat(),
                     finished=None)
    try:
        result = run_ingest()
        _last_run.update(status="ok", files=result["files"], cycle=result["cycle"])
    except Exception:
        log.exception("Ingest worker crashed")
        _last_run.update(status="error")
    finally:
        _last_run["finished"] = datetime.now(timezone.utc).isoformat()
        _ingest_lock.release()


if __name__ == "__main__":
    # CLI mode: run one ingest synchronously (useful for manual backfill/testing).
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(run_ingest())
