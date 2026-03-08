#!/usr/bin/env python3
"""
WHOOP → Intervals.icu Wellness Sync

Pulls recovery, sleep, and strain data from WHOOP and pushes it
to Intervals.icu wellness fields. Runs via GitHub Actions.

Required secrets:
  WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET, WHOOP_REFRESH_TOKEN,
  INTERVALS_KEY, ATHLETE_ID
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

# ── Config ──────────────────────────────────────

WHOOP_API = "https://api.prod.whoop.com/developer/v1"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
INTERVALS_API = "https://intervals.icu/api/v1"

WHOOP_CLIENT_ID = os.environ["WHOOP_CLIENT_ID"]
WHOOP_CLIENT_SECRET = os.environ["WHOOP_CLIENT_SECRET"]
WHOOP_REFRESH_TOKEN = os.environ["WHOOP_REFRESH_TOKEN"]
INTERVALS_KEY = os.environ["INTERVALS_KEY"]
ATHLETE_ID = os.environ["ATHLETE_ID"]


# ── WHOOP Auth ──────────────────────────────────

def whoop_get_access_token():
    """Exchange refresh token for access token."""
    resp = requests.post(WHOOP_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": WHOOP_REFRESH_TOKEN,
        "client_id": WHOOP_CLIENT_ID,
        "client_secret": WHOOP_CLIENT_SECRET,
    }, timeout=15)
    resp.raise_for_status()
    tokens = resp.json()
    new_refresh = tokens.get("refresh_token", WHOOP_REFRESH_TOKEN)
    if new_refresh != WHOOP_REFRESH_TOKEN:
        print("::warning::WHOOP refresh token rotated — update WHOOP_REFRESH_TOKEN secret.")
    return tokens["access_token"]


def whoop_get(access_token, path, params=None):
    """Make authenticated WHOOP API request."""
    resp = requests.get(
        f"{WHOOP_API}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Intervals.icu API ───────────────────────────

def intervals_put_wellness(date_str, data):
    """Update wellness data for a specific date in Intervals.icu."""
    url = f"{INTERVALS_API}/athlete/{ATHLETE_ID}/wellness/{date_str}"
    resp = requests.put(
        url,
        json=data,
        auth=("API_KEY", INTERVALS_KEY),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Sync Logic ──────────────────────────────────

def sync_recovery_and_sleep(access_token, days=3):
    """Sync WHOOP recovery + sleep → Intervals.icu wellness."""
    print(f"Syncing {days} days of recovery & sleep data...")

    # Get recovery cycles
    cycles = whoop_get(access_token, "/cycle", params={"limit": days})
    records = cycles.get("records", [])

    # Get sleep records
    sleeps = whoop_get(access_token, "/activity/sleep", params={"limit": days})
    sleep_records = sleeps.get("records", [])
    sleep_by_date = {}
    for s in sleep_records:
        d = s.get("start", "")[:10]
        if d:
            sleep_by_date[d] = s

    synced = 0
    for cycle in records:
        cycle_id = cycle.get("id")
        date_str = cycle.get("start", "")[:10]
        if not date_str:
            continue

        # Get recovery for this cycle
        try:
            recovery = whoop_get(access_token, f"/cycle/{cycle_id}/recovery")
        except requests.HTTPError:
            recovery = None

        # Build wellness payload
        wellness = {}
        score = recovery.get("score", {}) if recovery else {}

        if score.get("resting_heart_rate"):
            wellness["restingHR"] = score["resting_heart_rate"]
        if score.get("hrv_rmssd_milli"):
            wellness["hrvRMSSD"] = round(score["hrv_rmssd_milli"], 1)
        if score.get("spo2_percentage"):
            wellness["spO2"] = round(score["spo2_percentage"], 1)

        # Map WHOOP recovery score to comments for visibility
        recovery_pct = score.get("recovery_score")
        comments_parts = []
        if recovery_pct is not None:
            zone = "green" if recovery_pct >= 67 else "yellow" if recovery_pct >= 34 else "red"
            comments_parts.append(f"WHOOP Recovery: {recovery_pct}% ({zone})")

        # Strain from cycle
        cycle_score = cycle.get("score", {})
        strain = cycle_score.get("strain")
        if strain is not None:
            comments_parts.append(f"WHOOP Strain: {strain:.1f}")

        if comments_parts:
            wellness["comments"] = " | ".join(comments_parts)

        # Sleep data
        sleep = sleep_by_date.get(date_str)
        if sleep and sleep.get("score"):
            ss = sleep["score"]
            total_sleep_ms = ss.get("total_sleep_time_milli", 0)
            if total_sleep_ms:
                wellness["sleepTime"] = round(total_sleep_ms / 1000)  # seconds
            efficiency = ss.get("sleep_efficiency_percentage")
            if efficiency:
                # Map efficiency (0-100%) to sleep quality (1-5)
                wellness["sleepQuality"] = max(1, min(5, round(efficiency / 20)))

        if wellness:
            try:
                intervals_put_wellness(date_str, wellness)
                print(f"  {date_str}: OK"
                      f" (RHR={wellness.get('restingHR', '-')}"
                      f", HRV={wellness.get('hrvRMSSD', '-')}"
                      f", Recovery={recovery_pct or '-'}%"
                      f", Sleep={round(total_sleep_ms/3600000, 1) if sleep and sleep.get('score') else '-'}h)")
                synced += 1
            except requests.HTTPError as e:
                print(f"  {date_str}: FAILED - {e}")
        else:
            print(f"  {date_str}: no data to sync")

    return synced, len(records)


def main():
    days = int(os.environ.get("SYNC_DAYS", "3"))
    print("=== WHOOP → Intervals.icu Sync ===")
    print(f"Athlete: {ATHLETE_ID}")
    print(f"Days: {days}\n")

    access_token = whoop_get_access_token()
    print("WHOOP auth: OK\n")

    synced, total = sync_recovery_and_sleep(access_token, days=days)
    print(f"\nDone. Synced {synced}/{total} days.")


if __name__ == "__main__":
    main()
