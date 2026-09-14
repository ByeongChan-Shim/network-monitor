#!/usr/bin/env python3
"""Ping network targets and store each result in SQLite."""

import argparse
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("network.db")
CHECK_INTERVAL_SECONDS = 1.0

# Start with one target. Add more IP addresses or host names later.
TARGETS = ["8.8.8.8", "192.168.0.1", "203.250.77.254"]

LATENCY_PATTERN = re.compile(r"time[=<]([0-9.]+)\s*ms")


def create_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS network_check (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            target TEXT NOT NULL,
            target_type TEXT,
            success INTEGER NOT NULL,
            latency_ms REAL,
            error_type TEXT,
            error_message TEXT
        )
        """
    )
    connection.commit()


def ping(target):
    """Return success, latency in ms (or None), error type, and message."""
    try:
        result = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", "1", target],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return False, None, "timeout", "ping command timed out"
    except OSError as error:
        return False, None, "command_error", str(error)

    output = (result.stdout + result.stderr).strip()
    match = LATENCY_PATTERN.search(output)
    if result.returncode == 0 and match:
        return True, float(match.group(1)), None, None

    if "100% packet loss" in output or "Destination Host Unreachable" in output:
        error_type = "unreachable"
    else:
        error_type = "ping_failed"
    error_message = output.splitlines()[-1] if output else "ping returned no output"
    return False, None, error_type, error_message


def save_result(connection, target, success, latency_ms, error_type, error_message):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    connection.execute(
        """
        INSERT INTO network_check
            (timestamp, target, target_type, success, latency_ms, error_type, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            target,
            "ip",
            int(success),
            latency_ms,
            error_type,
            error_message,
        ),
    )
    connection.commit()
    status = f"{latency_ms:.2f} ms" if success else f"FAILED ({error_type})"
    print(f"{timestamp}  {target:15}  {status}", flush=True)


def collect_once(connection):
    for target in TARGETS:
        success, latency_ms, error_type, error_message = ping(target)
        save_result(connection, target, success, latency_ms, error_type, error_message)


def main():
    parser = argparse.ArgumentParser(description="Store ping results in SQLite.")
    parser.add_argument("--once", action="store_true", help="Run one check then exit.")
    arguments = parser.parse_args()

    with sqlite3.connect(DATABASE_PATH) as connection:
        create_table(connection)
        if arguments.once:
            collect_once(connection)
            return

        print("Collecting every 1 second. Press Ctrl+C to stop.")
        next_run = time.monotonic()
        try:
            while True:
                collect_once(connection)
                next_run += CHECK_INTERVAL_SECONDS
                time.sleep(max(0, next_run - time.monotonic()))
        except KeyboardInterrupt:
            print("\nCollector stopped.")


if __name__ == "__main__":
    main()

