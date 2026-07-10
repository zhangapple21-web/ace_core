#!/usr/bin/env python3
"""
ACE Heartbeat - Silent background heartbeat
============================================

Default: silent (logs to file only)
  - Logs: 02_MEMORY/logs/heartbeat_YYYYMMDD.log
  - No console output unless --verbose
"""
import os, sys, json, time, argparse, logging
from pathlib import Path
from datetime import datetime

WORKSPACE = Path(__file__).parent.parent
sys.path.insert(0, str(WORKSPACE))

import importlib.util

def import_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

try:
    ef = import_module(WORKSPACE / "04_PROTOCOLS" / "environment_first.py")
    lm = import_module(WORKSPACE / "04_PROTOCOLS" / "local_miner.py")
    ops_004 = import_module(WORKSPACE / "04_PROTOCOLS" / "ops_004_recovery_first.py")
    mem = import_module(WORKSPACE / "06_RUNTIME" / "core" / "memory_manager.py")
    ace_logger = import_module(WORKSPACE / "06_RUNTIME" / "core" / "ace_logger.py")
    env_sensor_mod = import_module(WORKSPACE / "04_PROTOCOLS" / "environment_sensor.py")

    scan_directory = ef.scan_directory
    build_recovery_graph = ef.build_recovery_graph
    task_signal_discovery = lm.task_signal_discovery
    task_archivist = lm.task_archivist
    ops_004_check = ops_004.recovery_first
    MemoryManager = mem.MemoryManager
    get_logger = ace_logger.get_logger
    silence_all = ace_logger.silence_all
    EnvironmentSensor = env_sensor_mod.EnvironmentSensor
    SituationBuilder = env_sensor_mod.SituationBuilder
except Exception as e:
    print(f"[HEARTBEAT] Import error: {e}", file=sys.stderr)
    sys.exit(1)


def beat(log):
    ts = datetime.now().isoformat()
    beat_id = ts.replace("-", "").replace(":", "").replace(".", "")[:15]
    log.info(f"=== Heartbeat {beat_id} ===")
    
    report = {
        "beat_id": beat_id,
        "time": ts,
        "status": "ok",
        "steps": {},
    }

    mm = MemoryManager()

    # OPS-004 Recovery First
    try:
        ops_004 = ops_004_check(check_only=True)
        report["ops_004_status"] = ops_004.get("summary", {})
        mm.save_memory("heartbeat", f"ops_004_{beat_id}", ops_004)
        if not ops_004.get("summary", {}).get("ready", False):
            log.warning(f"OPS-004 not ready: {ops_004['summary']}")
    except Exception as e:
        report["ops_004_status"] = {"error": str(e)}
        log.error(f"OPS-004 error: {e}")

    # EFP
    try:
        idx = scan_directory(WORKSPACE, max_depth=3)
        report["steps"]["efp"] = {
            "files": idx["files_total"],
            "recovery_assets": len(idx["recovery_assets"])
        }
        mm.save_memory("environment", "latest_scan", idx)
        log.info(f"EFP: {idx['files_total']} files, {len(idx['recovery_assets'])} recovery assets")
    except Exception as e:
        report["steps"]["efp"] = {"error": str(e)}
        log.error(f"EFP error: {e}")

    # Signal
    try:
        sig = task_signal_discovery()
        report["steps"]["signal"] = {"status": sig.get("status"), "model": sig.get("model")}
        log.info(f"Signal: {sig.get('status')}")
    except Exception as e:
        report["steps"]["signal"] = {"error": str(e)}
        log.error(f"Signal error: {e}")

    # Archivist
    try:
        arc = task_archivist()
        report["steps"]["archivist"] = {"status": arc.get("status"), "model": arc.get("model")}
        log.info(f"Archivist: {arc.get('status')}")
    except Exception as e:
        report["steps"]["archivist"] = {"error": str(e)}
        log.error(f"Archivist error: {e}")

    # ENV-001: Environment Sensor
    try:
        sensor = EnvironmentSensor()
        builder = SituationBuilder()
        obs = sensor.scan_all(sources=["local", "providers"])
        situation = builder.build(obs)
        report["steps"]["env_sensor"] = {
            "total": situation["total_observations"],
            "new": situation["new_observations"],
            "high_priority": len(situation["high_priority"]),
        }
        if situation["high_priority"]:
            log.warning(f"EnvSensor: {len(situation['high_priority'])} high priority items")
        else:
            log.info(f"EnvSensor: {situation['new_observations']} new observations")
    except Exception as e:
        report["steps"]["env_sensor"] = {"error": str(e)}
        log.error(f"EnvSensor error: {e}")

    # Save
    mm.save_memory("heartbeat", f"beat_{beat_id}", report)
    log.info("Heartbeat saved")
    return report


def loop(interval_min=15, log=None):
    log.info(f"Heartbeat loop started (interval={interval_min}min)")
    while True:
        beat(log)
        time.sleep(interval_min * 60)


def main():
    parser = argparse.ArgumentParser(description="ACE Heartbeat (silent by default)")
    parser.add_argument("--loop", action="store_true", help="Run as background loop")
    parser.add_argument("--interval", type=int, default=15, help="Interval in minutes")
    parser.add_argument("--verbose", action="store_true", help="Print to console")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       default="INFO", help="Log level")
    args = parser.parse_args()

    log_level = getattr(logging, args.log_level)
    log = get_logger("heartbeat", level=log_level, silent=not args.verbose)
    silence_all()

    if args.loop:
        loop(args.interval, log=log)
    else:
        result = beat(log)
        if args.verbose:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()