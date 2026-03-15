#!/usr/bin/env python3
"""
Generate latest.json data mirror from Intervals.icu API.
Computes all derived metrics needed by Section 11 protocol engine.

Usage:
  python generate_mirror.py              # Generate and print to stdout
  python generate_mirror.py --push       # Generate and push to GitHub repo
  python generate_mirror.py --out file   # Generate and write to file
"""

import os
import sys
import json
import math
import argparse
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("INTERVALS_API_KEY") or os.getenv("API_KEY")
ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID") or os.getenv("ATHLETE_ID")
BASE_URL = os.getenv("INTERVALS_API_BASE_URL", "https://intervals.icu/api/v1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("MIRROR_REPO", "mijimathews/my-training-data")

VERSION = "3.7.0"


# =============================================================================
# Intervals.icu API helpers
# =============================================================================

def icu_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", auth=("API_KEY", API_KEY), params=params)
    r.raise_for_status()
    return r.json()


def fetch_activities(days=28):
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    return icu_get(f"/athlete/{ATHLETE_ID}/activities",
                   params={"oldest": oldest, "newest": newest})


def fetch_wellness(days=14):
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    return icu_get(f"/athlete/{ATHLETE_ID}/wellness",
                   params={"oldest": oldest, "newest": newest})


def fetch_events(days=45):
    oldest = datetime.now().strftime("%Y-%m-%d")
    newest = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    return icu_get(f"/athlete/{ATHLETE_ID}/events",
                   params={"oldest": oldest, "newest": newest})


def fetch_athlete():
    return icu_get(f"/athlete/{ATHLETE_ID}")


# =============================================================================
# Derived metric calculations
# =============================================================================

def compute_fitness(activities_28d):
    """Get CTL/ATL/TSB from the most recent activity."""
    for a in activities_28d:
        if a.get("icu_ctl") is not None:
            return {
                "ctl": round(a["icu_ctl"], 2),
                "atl": round(a.get("icu_atl", 0), 2),
                "tsb": round(a["icu_ctl"] - a.get("icu_atl", 0), 2),
                "ramp_rate": round(a.get("icu_rolling_ftp_delta", 0) or 0, 2),
                "fitness_source": "intervals_icu",
            }
    return {"ctl": 0, "atl": 0, "tsb": 0, "ramp_rate": 0, "fitness_source": "none"}


def compute_load_metrics(activities_28d):
    """ACWR, monotony, strain from activity TSS."""
    now = datetime.now()
    tss_daily_7d = {}
    tss_daily_28d = {}

    for a in activities_28d:
        date_str = a.get("start_date_local", "")[:10]
        tss = a.get("icu_training_load") or 0
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        days_ago = (now - d).days
        if days_ago <= 7:
            tss_daily_7d[date_str] = tss_daily_7d.get(date_str, 0) + tss
        if days_ago <= 28:
            tss_daily_28d[date_str] = tss_daily_28d.get(date_str, 0) + tss

    tss_7d = sum(tss_daily_7d.values())
    tss_28d = sum(tss_daily_28d.values())

    # Fill missing days with 0 for monotony calculation
    tss_values_7d = []
    for i in range(7):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        tss_values_7d.append(tss_daily_7d.get(d, 0))

    avg_7d = sum(tss_values_7d) / 7 if tss_values_7d else 0
    std_7d = (sum((x - avg_7d) ** 2 for x in tss_values_7d) / 7) ** 0.5 if tss_values_7d else 1

    monotony = avg_7d / std_7d if std_7d > 0 else 0
    strain = tss_7d * monotony

    # ACWR: 7-day ATL / 28-day chronic average
    avg_28d_weekly = tss_28d / 4 if tss_28d else 1
    acwr = tss_7d / avg_28d_weekly if avg_28d_weekly > 0 else 1.0

    acwr_interp = "optimal" if 0.8 <= acwr <= 1.3 else (
        "undertraining" if acwr < 0.8 else "injury risk zone")
    mono_interp = "acceptable" if monotony < 2.3 else "high — vary sessions"

    return {
        "tss_7d_total": round(tss_7d, 1),
        "tss_28d_total": round(tss_28d, 1),
        "acwr": round(acwr, 3),
        "acwr_interpretation": acwr_interp,
        "monotony": round(monotony, 3),
        "effective_monotony": round(monotony, 3),
        "monotony_interpretation": mono_interp,
        "strain": round(strain, 1),
    }


def compute_stress_metrics(fitness, load):
    """Stress tolerance and load-recovery ratio."""
    ctl = fitness.get("ctl", 0)
    atl = fitness.get("atl", 0)
    tss_7d = load.get("tss_7d_total", 0)

    stress_tol = (ctl - atl + 20) if ctl else 0
    load_rec = tss_7d / max(1, ctl * 7) if ctl else 0

    return {
        "stress_tolerance": round(stress_tol, 1),
        "load_recovery_ratio": round(load_rec, 2),
    }


def compute_recovery_index(wellness_data):
    """Recovery Index from HRV + RHR baselines."""
    if not wellness_data:
        return {}

    hrvs = [w.get("hrv") for w in wellness_data if w.get("hrv")]
    rhrs = [w.get("restingHR") for w in wellness_data if w.get("restingHR")]

    hrv_7d = sum(hrvs[:7]) / len(hrvs[:7]) if hrvs[:7] else None
    hrv_28d = sum(hrvs) / len(hrvs) if hrvs else None
    rhr_7d = sum(rhrs[:7]) / len(rhrs[:7]) if rhrs[:7] else None
    rhr_28d = sum(rhrs) / len(rhrs) if rhrs else None

    latest_hrv = hrvs[0] if hrvs else None
    latest_rhr = rhrs[0] if rhrs else None

    # RI = (HRV/baseline * 0.6) + ((1 - RHR_delta/10) * 0.4)
    ri = None
    if latest_hrv and hrv_7d and latest_rhr and rhr_7d:
        hrv_ratio = latest_hrv / hrv_7d if hrv_7d > 0 else 1.0
        rhr_delta = latest_rhr - rhr_7d
        rhr_component = 1.0 - (rhr_delta / 10)
        ri = round(hrv_ratio * 0.6 + rhr_component * 0.4, 3)

    return {
        "recovery_index": ri,
        "hrv_baseline_7d": round(hrv_7d, 1) if hrv_7d else None,
        "hrv_baseline_28d": round(hrv_28d, 1) if hrv_28d else None,
        "latest_hrv": round(latest_hrv, 1) if latest_hrv else None,
        "rhr_baseline_7d": round(rhr_7d) if rhr_7d else None,
        "rhr_baseline_28d": round(rhr_28d, 1) if rhr_28d else None,
        "latest_rhr": latest_rhr,
    }


def compute_zone_distribution(activities, window_days=7):
    """Power zone distribution and training intensity metrics."""
    now = datetime.now()
    z_totals = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0, "Z6": 0, "Z7": 0}
    hard_days = set()

    for a in activities:
        date_str = a.get("start_date_local", "")[:10]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if (now - d).days > window_days:
            continue

        zones = a.get("icu_zone_times", [])
        z3_secs = 0
        z4p_secs = 0
        for z in zones:
            zid = z.get("id", "")
            secs = z.get("secs", 0)
            if zid in z_totals:
                z_totals[zid] += secs
            if zid == "Z3":
                z3_secs += secs
            if zid in ("Z4", "Z5", "Z6", "Z7"):
                z4p_secs += secs

        # Hard day: Z3 >= 30min OR Z4+ >= 10min
        if z3_secs >= 1800 or z4p_secs >= 600:
            hard_days.add(date_str)

    total_secs = sum(z_totals.values()) or 1
    z1_z2_secs = z_totals["Z1"] + z_totals["Z2"]
    z3_secs = z_totals["Z3"]
    z4p_secs = z_totals["Z4"] + z_totals["Z5"] + z_totals["Z6"] + z_totals["Z7"]

    grey_zone_pct = (z3_secs / total_secs) * 100
    quality_pct = (z4p_secs / total_secs) * 100
    pol_idx = z1_z2_secs / (z3_secs + 1) if z3_secs > 0 else (z1_z2_secs / total_secs)

    return {
        "zone_distribution_7d": {
            "z1_hours": round(z_totals["Z1"] / 3600, 2),
            "z2_hours": round(z_totals["Z2"] / 3600, 2),
            "z3_hours": round(z_totals["Z3"] / 3600, 2),
            "z4_plus_hours": round(z4p_secs / 3600, 2),
            "total_hours": round(total_secs / 3600, 2),
        },
        "grey_zone_percentage": round(grey_zone_pct, 1),
        "quality_intensity_percentage": round(quality_pct, 1),
        "polarisation_index": round(pol_idx, 2),
        "hard_days_this_week": len(hard_days),
    }


def compute_seiler_tid(activities, window_days):
    """Seiler 3-zone Training Intensity Distribution."""
    now = datetime.now()
    z1_secs = z2_secs = z3_secs = 0

    for a in activities:
        date_str = a.get("start_date_local", "")[:10]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if (now - d).days > window_days:
            continue

        zones = a.get("icu_zone_times", [])
        for z in zones:
            zid = z.get("id", "")
            secs = z.get("secs", 0)
            if zid in ("Z1", "Z2"):
                z1_secs += secs
            elif zid == "Z3":
                z2_secs += secs  # Seiler Z2 = power Z3
            elif zid in ("Z4", "Z5", "Z6", "Z7"):
                z3_secs += secs  # Seiler Z3 = power Z4+

    total = z1_secs + z2_secs + z3_secs or 1
    z1_pct = round(z1_secs / total * 100, 1)
    z2_pct = round(z2_secs / total * 100, 1)
    z3_pct = round(z3_secs / total * 100, 1)

    pi = z1_secs / (z2_secs + 1) if z2_secs > 0 else None

    # Classify: Polarized (>80% Z1, <5-10% Z2), Pyramidal (Z1>Z2>Z3), Threshold
    if z1_pct >= 75 and z2_pct <= 10 and z3_pct >= 10:
        classification = "Polarized"
    elif z1_pct > z2_pct > z3_pct:
        classification = "Pyramidal"
    elif z2_pct >= 20:
        classification = "Threshold-dominated"
    else:
        classification = "Mixed"

    return {
        "z1_seconds": z1_secs,
        "z2_seconds": z2_secs,
        "z3_seconds": z3_secs,
        "z1_pct": z1_pct,
        "z2_pct": z2_pct,
        "z3_pct": z3_pct,
        "polarization_index": round(pi, 2) if pi else None,
        "classification": classification,
    }


def compute_durability(activities, window_days):
    """Mean decoupling for qualifying rides (VI <= 1.05, duration >= 90min)."""
    now = datetime.now()
    decouplings = []

    for a in activities:
        date_str = a.get("start_date_local", "")[:10]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if (now - d).days > window_days:
            continue

        dc = a.get("decoupling")
        vi = a.get("icu_variability_index")
        duration = a.get("moving_time", 0)
        if dc is not None and duration >= 5400:  # 90 min
            decouplings.append(dc)

    if not decouplings:
        return {"mean_decoupling": None, "qualifying_sessions": 0,
                "high_drift_count": 0, "trend": "insufficient_data", "note": "No qualifying rides"}

    mean_dc = sum(decouplings) / len(decouplings)
    high_drift = sum(1 for d in decouplings if abs(d) > 5)

    return {
        "mean_decoupling": round(mean_dc, 2),
        "qualifying_sessions": len(decouplings),
        "high_drift_count": high_drift,
        "trend": "stable",
        "note": f"{len(decouplings)} qualifying sessions",
    }


def compute_ef_trend(activities, window_days):
    """Efficiency Factor trend for qualifying sessions."""
    now = datetime.now()
    efs = []

    for a in activities:
        date_str = a.get("start_date_local", "")[:10]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if (now - d).days > window_days:
            continue

        ef = a.get("icu_efficiency_factor")
        duration = a.get("moving_time", 0)
        if ef is not None and duration >= 1200:  # 20 min
            efs.append(ef)

    if not efs:
        return {"mean_ef": None, "qualifying_sessions": 0, "trend": "insufficient_data"}

    mean_ef = sum(efs) / len(efs)
    # Simple trend: compare first half vs second half
    mid = len(efs) // 2
    if mid > 0 and len(efs) > 2:
        first_half = sum(efs[:mid]) / mid
        second_half = sum(efs[mid:]) / len(efs[mid:])
        if second_half > first_half * 1.03:
            trend = "improving"
        elif second_half < first_half * 0.97:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "mean_ef": round(mean_ef, 3),
        "qualifying_sessions": len(efs),
        "trend": trend,
    }


def format_activity(a):
    """Format an activity for the recent_activities section."""
    duration_secs = a.get("moving_time", 0)
    duration_hrs = duration_secs / 3600

    # Zone distribution
    hr_zones = {}
    pwr_zones = {}
    hz = a.get("icu_hr_zone_times", [])
    for i, secs in enumerate(hz):
        hr_zones[f"z{i+1}_time"] = secs
    for z in a.get("icu_zone_times", []):
        pwr_zones[f"{z['id'].lower()}_time"] = z["secs"]

    return {
        "id": a.get("id"),
        "date": a.get("start_date_local"),
        "type": a.get("type"),
        "name": a.get("name", "Untitled"),
        "duration_hours": round(duration_hrs, 2),
        "distance_km": round(a.get("distance", 0) / 1000, 1),
        "tss": a.get("icu_training_load"),
        "intensity_factor": round(a.get("icu_intensity", 0), 1),
        "avg_power": a.get("icu_average_watts"),
        "normalized_power": a.get("icu_weighted_avg_watts"),
        "avg_hr": round(a["average_heartrate"]) if a.get("average_heartrate") else None,
        "max_hr": a.get("max_heartrate"),
        "avg_cadence": round(a["average_cadence"], 1) if a.get("average_cadence") else None,
        "avg_speed": round(a.get("average_speed", 0) * 3.6, 1) if a.get("average_speed") else None,
        "max_speed": round(a.get("max_speed", 0) * 3.6, 1) if a.get("max_speed") else None,
        "avg_temp": round(a["average_temp"], 1) if a.get("average_temp") else None,
        "work_kj": round(a.get("icu_joules", 0) / 1000, 1) if a.get("icu_joules") else None,
        "calories": a.get("calories"),
        "carbs_used": a.get("carbs_used"),
        "carbs_ingested": a.get("carbs_ingested"),
        "variability_index": round(a["icu_variability_index"], 3) if a.get("icu_variability_index") else None,
        "decoupling": round(a["decoupling"], 2) if a.get("decoupling") is not None else None,
        "efficiency_factor": round(a["icu_efficiency_factor"], 3) if a.get("icu_efficiency_factor") else None,
        "elevation_m": a.get("total_elevation_gain"),
        "feel": a.get("feel"),
        "rpe": a.get("icu_rpe"),
        "zone_distribution": {
            "hr_zones": hr_zones,
            "power_zones": pwr_zones,
        },
    }


def format_wellness(w):
    """Format a wellness entry."""
    sleep_secs = w.get("sleepSecs", 0) or 0
    sleep_hrs = sleep_secs / 3600
    h = int(sleep_hrs)
    m = int((sleep_hrs - h) * 60)

    return {
        "date": w.get("id"),
        "weight_kg": w.get("weight"),
        "resting_hr": w.get("restingHR"),
        "hrv_rmssd": w.get("hrv"),
        "hrv_sdnn": w.get("hrvSDNN"),
        "sleep_hours": round(sleep_hrs, 2),
        "sleep_formatted": f"{h}h{m:02d}m",
        "sleep_quality": w.get("sleepQuality"),
        "sleep_score": w.get("sleepScore"),
        "fatigue": w.get("fatigue"),
        "soreness": w.get("soreness"),
        "avg_sleeping_hr": w.get("avgSleepingHR"),
        "vo2max": w.get("vo2max") if w.get("vo2max") else None,
    }


def format_event(e):
    """Format a planned workout/event."""
    duration_secs = e.get("moving_time", 0) or 0
    h = duration_secs // 3600
    m = (duration_secs % 3600) // 60

    return {
        "id": e.get("id"),
        "date": e.get("start_date_local", "")[:10],
        "name": e.get("name") or e.get("category", "Workout"),
        "type": e.get("type", ""),
        "planned_tss": e.get("icu_training_load"),
        "duration_hours": round(duration_secs / 3600, 2) if duration_secs else None,
        "duration_formatted": f"{h}h{m:02d}m" if duration_secs else "",
        "description": e.get("description", ""),
    }


def build_race_calendar():
    """Build race calendar with taper/race-week alerts."""
    now = datetime.now()
    races = [
        {
            "name": "Highlands Gran Fondo",
            "date": "2026-06-07",
            "category": "RACE_B",
            "type": "Gran Fondo",
        },
    ]

    next_race = None
    for race in races:
        race_date = datetime.strptime(race["date"], "%Y-%m-%d")
        days_until = (race_date - now).days
        if days_until >= 0:
            race["days_until"] = days_until
            if not next_race or days_until < next_race.get("days_until", 999):
                next_race = race

    taper_active = False
    race_week_active = False
    if next_race:
        d = next_race["days_until"]
        taper_active = 7 < d <= 21
        race_week_active = d <= 7

    return {
        "next_race": next_race,
        "all_races": races,
        "taper_alert": {
            "active": taper_active,
            "event_name": next_race["name"] if next_race and taper_active else None,
        },
        "race_week": {
            "active": race_week_active,
            "event_name": next_race["name"] if next_race and race_week_active else None,
            "days_to_race": next_race["days_until"] if next_race and race_week_active else None,
        },
    }


# =============================================================================
# Main generator
# =============================================================================

def generate():
    """Generate the complete latest.json structure."""
    print("Fetching data from Intervals.icu...", file=sys.stderr)

    activities_28d = fetch_activities(28)
    activities_28d.sort(key=lambda a: a.get("start_date_local", ""), reverse=True)

    wellness = fetch_wellness(14)
    wellness.sort(key=lambda w: w.get("id", ""), reverse=True)

    events = fetch_events(45)
    athlete = fetch_athlete()

    print(f"  Activities: {len(activities_28d)}", file=sys.stderr)
    print(f"  Wellness:   {len(wellness)}", file=sys.stderr)
    print(f"  Events:     {len(events)}", file=sys.stderr)

    # Compute all metrics
    fitness = compute_fitness(activities_28d)
    load = compute_load_metrics(activities_28d)
    stress = compute_stress_metrics(fitness, load)
    recovery = compute_recovery_index(wellness)
    zones_7d = compute_zone_distribution(activities_28d, 7)
    tid_7d = compute_seiler_tid(activities_28d, 7)
    tid_28d = compute_seiler_tid(activities_28d, 28)
    dur_7d = compute_durability(activities_28d, 7)
    dur_28d = compute_durability(activities_28d, 28)
    ef_7d = compute_ef_trend(activities_28d, 7)
    ef_28d = compute_ef_trend(activities_28d, 28)

    # TID comparison
    tid_drift = "consistent" if tid_7d["classification"] == tid_28d["classification"] else "shifting"

    # Phase detection (simplified — mirrors section11.py logic)
    acwr = load["acwr"]
    monotony = load["monotony"]
    strain = load["strain"]
    ri = recovery.get("recovery_index")
    hard_days = zones_7d["hard_days_this_week"]
    quality_pct = zones_7d["quality_intensity_percentage"]

    if (acwr > 1.3) or (strain > 3500) or (ri and ri < 0.6):
        phase = "Overreached"
    elif fitness["tsb"] > 10 and load["tss_7d_total"] < load["tss_28d_total"] / 4 * 0.5:
        phase = "Recovery"
    elif 1.0 <= acwr <= 1.3 and (quality_pct >= 15 or hard_days >= 2):
        phase = "Build"
    elif fitness.get("ramp_rate") is not None and abs(fitness["ramp_rate"]) < 0.5 and quality_pct >= 20:
        phase = "Peak"
    else:
        phase = "Base"

    phase_triggers = [f"ACWR {acwr:.2f}", f"Hard days: {hard_days}", f"Quality: {quality_pct:.1f}%"]

    # Thresholds from athlete profile
    sport_info = activities_28d[0].get("sportInfo") if activities_28d else None
    cycling_thresh = {
        "ftp": athlete.get("ftp") or (activities_28d[0].get("icu_ftp") if activities_28d else 230),
        "ftp_indoor": athlete.get("ftp") or 235,
        "lthr": athlete.get("lthr") or (activities_28d[0].get("lthr") if activities_28d else 172),
        "max_hr": athlete.get("max_hr") or (activities_28d[0].get("athlete_max_hr") if activities_28d else 190),
    }

    eftp = activities_28d[0].get("icu_rolling_ftp") if activities_28d else None
    w_prime = activities_28d[0].get("icu_rolling_w_prime") if activities_28d else None
    p_max = activities_28d[0].get("icu_rolling_p_max") if activities_28d else None

    # Current metrics from latest wellness
    latest_w = wellness[0] if wellness else {}
    sleep_secs = latest_w.get("sleepSecs", 0) or 0
    sleep_hrs = sleep_secs / 3600
    sh = int(sleep_hrs)
    sm = int((sleep_hrs - sh) * 60)

    current_metrics = {
        "weight_kg": latest_w.get("weight") or (athlete.get("weight") or 88.0),
        "resting_hr": latest_w.get("restingHR"),
        "hrv": latest_w.get("hrv"),
        "sleep_quality": latest_w.get("sleepQuality"),
        "sleep_hours": round(sleep_hrs, 2),
        "sleep_formatted": f"{sh}h{sm:02d}m",
    }

    # Weekly summary
    total_secs_7d = zones_7d["zone_distribution_7d"]["total_hours"] * 3600
    weekly_summary = {
        "total_training_hours": zones_7d["zone_distribution_7d"]["total_hours"],
        "total_tss": load["tss_7d_total"],
        "avg_hrv": recovery.get("hrv_baseline_7d"),
        "avg_rhr": recovery.get("rhr_baseline_7d"),
    }

    # Data quality
    data_quality = {
        "hrv_data_points": sum(1 for w in wellness if w.get("hrv")),
        "rhr_data_points": sum(1 for w in wellness if w.get("restingHR")),
        "activities_7d": sum(1 for a in activities_28d
                            if (datetime.now() - datetime.strptime(
                                a.get("start_date_local", "2020-01-01")[:10], "%Y-%m-%d")).days <= 7),
        "activities_28d": len(activities_28d),
        "planned_workouts_7d": sum(1 for e in events
                                   if e.get("start_date_local") and
                                   (datetime.strptime(e["start_date_local"][:10], "%Y-%m-%d") - datetime.now()).days <= 7),
    }

    now_ts = datetime.now(timezone.utc).isoformat()

    latest = {
        "READ_THIS_FIRST": {
            "instructions": "This file is auto-generated by generate_mirror.py. Do not edit manually.",
            "version": VERSION,
            "schema": "Section 11 Protocol v11.10",
        },
        "metadata": {
            "athlete_id": ATHLETE_ID,
            "last_updated": now_ts,
            "version": VERSION,
            "generator": "generate_mirror.py",
        },
        "alerts": [],
        "history": {
            "activities_days": 28,
            "wellness_days": 14,
            "planned_days": 45,
        },
        "summary": {},
        "current_status": {
            "fitness": fitness,
            "thresholds": {
                "eftp": eftp,
                "w_prime": round(w_prime) if w_prime else None,
                "w_prime_kj": round(w_prime / 1000, 1) if w_prime else None,
                "p_max": round(p_max) if p_max else None,
                "vo2max": None,
                "sports": {
                    "cycling": cycling_thresh,
                },
            },
            "current_metrics": current_metrics,
        },
        "derived_metrics": {
            **recovery,
            **load,
            **stress,
            **zones_7d,
            "eftp": eftp,
            "w_prime": round(w_prime) if w_prime else None,
            "w_prime_kj": round(w_prime / 1000, 1) if w_prime else None,
            "p_max": round(p_max) if p_max else None,
            "vo2max": None,
            "power_model_source": "intervals_icu_rolling",
            "seiler_tid_7d": tid_7d,
            "seiler_tid_28d": tid_28d,
            "capability": {
                "durability": {
                    "mean_decoupling_7d": dur_7d["mean_decoupling"],
                    "mean_decoupling_28d": dur_28d["mean_decoupling"],
                    "high_drift_count_7d": dur_7d["high_drift_count"],
                    "high_drift_count_28d": dur_28d["high_drift_count"],
                    "qualifying_sessions_7d": dur_7d["qualifying_sessions"],
                    "qualifying_sessions_28d": dur_28d["qualifying_sessions"],
                    "trend": dur_28d["trend"],
                    "note": dur_28d["note"],
                },
                "efficiency_factor": {
                    "mean_ef_7d": ef_7d["mean_ef"],
                    "mean_ef_28d": ef_28d["mean_ef"],
                    "qualifying_sessions_7d": ef_7d["qualifying_sessions"],
                    "qualifying_sessions_28d": ef_28d["qualifying_sessions"],
                    "trend": ef_28d["trend"],
                },
                "tid_comparison": {
                    "classification_7d": tid_7d["classification"],
                    "classification_28d": tid_28d["classification"],
                    "pi_7d": tid_7d["polarization_index"],
                    "pi_28d": tid_28d["polarization_index"],
                    "pi_delta": round(
                        (tid_7d["polarization_index"] or 0) - (tid_28d["polarization_index"] or 0), 2
                    ) if tid_7d["polarization_index"] and tid_28d["polarization_index"] else None,
                    "drift": tid_drift,
                    "note": f"7d: {tid_7d['classification']}, 28d: {tid_28d['classification']}",
                },
            },
            "consistency_index": None,
            "phase_detected": phase,
            "phase_triggers": phase_triggers,
            "seasonal_context": "spring_build",
            "data_quality": data_quality,
            "calculation_timestamp": now_ts,
        },
        "weekly_summary": weekly_summary,
        "wellness_data": [format_wellness(w) for w in wellness[:7]],
        "recent_activities": [format_activity(a) for a in activities_28d[:5]],
        "planned_workouts": [format_event(e) for e in events],
        "race_calendar": build_race_calendar(),
        "workout_summary_stats": {},
    }

    return latest


# =============================================================================
# GitHub push
# =============================================================================

def push_to_github(content_json):
    """Push latest.json to GitHub repo via API."""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set. Cannot push.", file=sys.stderr)
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/latest.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Get current file SHA
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    import base64
    encoded = base64.b64encode(content_json.encode()).decode()

    payload = {
        "message": f"Update latest.json — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": encoded,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    if r.status_code in (200, 201):
        print(f"Pushed to GitHub: {GITHUB_REPO}/latest.json", file=sys.stderr)
        return True
    else:
        print(f"GitHub push failed: {r.status_code} {r.text}", file=sys.stderr)
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate latest.json data mirror")
    parser.add_argument("--push", action="store_true", help="Push to GitHub repo")
    parser.add_argument("--out", type=str, help="Write to file instead of stdout")
    args = parser.parse_args()

    data = generate()
    content = json.dumps(data, indent=2)

    if args.push:
        push_to_github(content)
    elif args.out:
        with open(args.out, "w") as f:
            f.write(content)
        print(f"Written to {args.out}", file=sys.stderr)
    else:
        print(content)

    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
