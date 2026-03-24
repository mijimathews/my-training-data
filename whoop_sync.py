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

WHOOP_API = "https://api.prod.whoop.com/developer/v2"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
INTERVALS_API = "https://intervals.icu/api/v1"

WHOOP_CLIENT_ID = os.environ["WHOOP_CLIENT_ID"]
WHOOP_CLIENT_SECRET = os.environ["WHOOP_CLIENT_SECRET"]
WHOOP_REFRESH_TOKEN = os.environ["WHOOP_REFRESH_TOKEN"]
INTERVALS_KEY = os.environ["INTERVALS_KEY"]
ATHLETE_ID = os.environ["ATHLETE_ID"]


# ── WHOOP Auth ──────────────────────────────────

def _read_refresh_token():
    """Read refresh token from file (committed to repo) or env var."""
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whoop_refresh_token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
            if token:
                return token
    return WHOOP_REFRESH_TOKEN


def _save_refresh_token(new_token):
    """Save rotated refresh token to file and commit it."""
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whoop_refresh_token")
    with open(token_file, "w") as f:
        f.write(new_token + "\n")
    print(f"  Saved new refresh token to .whoop_refresh_token")


def whoop_get_access_token():
    """Exchange refresh token for access token."""
    refresh_token = _read_refresh_token()
    token_source = "file" if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whoop_refresh_token")
    ) else "env"
    print(f"  Using refresh token from: {token_source} (ends ...{refresh_token[-8:]})")
    resp = requests.post(WHOOP_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": WHOOP_CLIENT_ID,
        "client_secret": WHOOP_CLIENT_SECRET,
        "scope": "offline read:recovery read:sleep read:workout read:body_measurement read:cycles",
    }, timeout=15)
    if resp.status_code != 200:
        print(f"  Token exchange FAILED: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        print(f"  Hint: refresh token may be expired — re-authorize at")
        print(f"  https://app.whoop.com/oauth/authorize?client_id={WHOOP_CLIENT_ID}"
              f"&redirect_uri=http://localhost:8080&response_type=code"
              f"&scope=offline+read:recovery+read:sleep+read:workout+read:body_measurement+read:cycles")
        # If file token failed, try env var as fallback
        if token_source == "file" and refresh_token != WHOOP_REFRESH_TOKEN:
            print(f"\n  Retrying with env var token (ends ...{WHOOP_REFRESH_TOKEN[-8:]})...")
            resp = requests.post(WHOOP_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": WHOOP_REFRESH_TOKEN,
                "client_id": WHOOP_CLIENT_ID,
                "client_secret": WHOOP_CLIENT_SECRET,
                "scope": "offline read:recovery read:sleep read:workout read:body_measurement read:cycles",
            }, timeout=15)
            if resp.status_code == 200:
                print("  Env var token worked! Saving as new file token.")
                tokens = resp.json()
                new_refresh = tokens.get("refresh_token", WHOOP_REFRESH_TOKEN)
                _save_refresh_token(new_refresh)
                return tokens["access_token"]
            print(f"  Env var fallback also failed: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
    tokens = resp.json()
    new_refresh = tokens.get("refresh_token", refresh_token)
    if new_refresh != refresh_token:
        print("  WHOOP refresh token rotated.")
        _save_refresh_token(new_refresh)
    return tokens["access_token"]


def whoop_get(access_token, path, params=None):
    """Make authenticated WHOOP API request."""
    url = f"{WHOOP_API}{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"  WHOOP API error: {resp.status_code} {url}")
        print(f"  Response: {resp.text[:500]}")
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
    if resp.status_code != 200:
        print(f"  Intervals API error: {resp.status_code}")
        print(f"  Payload: {data}")
        print(f"  Response: {resp.text[:500]}")
    resp.raise_for_status()
    return resp.json()


# ── Sync Logic ──────────────────────────────────

def sync_recovery_and_sleep(access_token, days=3):
    """Sync WHOOP recovery + sleep → Intervals.icu wellness."""
    print(f"Syncing {days} days of recovery & sleep data...")

    # Get recovery records (v2 returns them directly)
    recoveries = whoop_get(access_token, "/recovery", params={"limit": days})
    recovery_records = recoveries.get("records", [])
    recovery_by_cycle = {}
    for rec in recovery_records:
        cid = rec.get("cycle_id")
        if cid:
            recovery_by_cycle[cid] = rec

    # Get sleep records
    sleeps = whoop_get(access_token, "/activity/sleep", params={"limit": days})
    sleep_records = sleeps.get("records", [])
    sleep_by_date = {}
    for s in sleep_records:
        d = s.get("start", "")[:10]
        if d:
            sleep_by_date[d] = s

    # Get cycles for dates and strain
    cycles = whoop_get(access_token, "/cycle", params={"limit": days})
    records = cycles.get("records", [])

    synced = 0
    for cycle in records:
        cycle_id = cycle.get("id")
        date_str = cycle.get("start", "")[:10]
        if not date_str:
            continue

        # Look up recovery for this cycle
        recovery = recovery_by_cycle.get(cycle_id)

        # Build wellness payload
        wellness = {}
        score = recovery.get("score", {}) if recovery else {}

        if score.get("resting_heart_rate"):
            wellness["restingHR"] = score["resting_heart_rate"]
        if score.get("hrv_rmssd_milli"):
            wellness["hrv"] = round(score["hrv_rmssd_milli"], 1)
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
                wellness["sleepSecs"] = round(total_sleep_ms / 1000)  # seconds
            efficiency = ss.get("sleep_efficiency_percentage")
            if efficiency:
                # Map efficiency (0-100%) to sleep quality (1-4)
                wellness["sleepQuality"] = max(1, min(4, round(efficiency / 25)))

        if wellness:
            try:
                intervals_put_wellness(date_str, wellness)
                print(f"  {date_str}: OK"
                      f" (RHR={wellness.get('restingHR', '-')}"
                      f", HRV={wellness.get('hrv', '-')}"
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
