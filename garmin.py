#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#pip install garminconnect python-dotenv


"""
Garmin lightweight fetch helpers:
- get_recent_activities(api, limit=7) -> list[dict]
- get_vo2max_today(api) -> float | None
- get_sleep_last_nd(api, ndays=7) -> list[dict]

No persistence. No schema changes. Minimal, tidy, import-friendly.

Usage (optional demo):
    python garmin_light.py --demo --limit 7 --sleep-days 7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# --- Optional credentials module (fallback to env) ---------------------------
try:
    from garmin_login import username as GC_USER, password as GC_PASS  # type: ignore
except Exception:  # pragma: no cover
    GC_USER = os.getenv("EMAIL")
    GC_PASS = os.getenv("PASSWORD")


# --- Login helpers -----------------------------------------------------------
def _token_login(token_dir: Path) -> Tuple[Optional[Garmin], Optional[str]]:
    """Try logging in using saved tokens in token_dir."""
    try:
        api = Garmin()
        api.login(str(token_dir))
        return api, None
    except (FileNotFoundError, GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        return None, str(e)
    except Exception as e:  # pragma: no cover
        return None, str(e)


def _credential_login(token_dir: Path, user: Optional[str], pw: Optional[str]) -> Tuple[Optional[Garmin], Optional[str]]:
    """Login with username/password and dump tokens to token_dir."""
    if not user or not pw:
        return None, "Credentials missing (garmin_login.username/password or EMAIL/PASSWORD env)."

    try:
        api = Garmin(email=user, password=pw, return_on_mfa=True)
        res1, res2 = api.login()  # may prompt MFA flow
        if res1 == "needs_mfa":
            return None, (
                "MFA required. Please complete login once via the official example/demo "
                "to create tokens in ~/.garminconnect."
            )
        token_dir.mkdir(parents=True, exist_ok=True)
        api.garth.dump(str(token_dir))
        return api, None
    except Exception as e:  # pragma: no cover
        return None, f"Credential login failed: {e}"


def get_api(token_dir: str | Path = "~/.garminconnect") -> Garmin:
    """
    Obtain an authenticated Garmin client.
    Prefers tokens in token_dir; falls back to credentials (env or garmin_login.py).
    """
    token_dir = Path(token_dir).expanduser()
    api, err = _token_login(token_dir)
    if api:
        return api

    api, err2 = _credential_login(token_dir, GC_USER, GC_PASS)
    if api:
        return api

    raise RuntimeError(f"Login failed.\n- Token error: {err}\n- Cred error: {err2}")


# --- Data normalization -------------------------------------------------------
def _normalize_activity(a: Dict[str, Any]) -> Dict[str, Any]:
    """Slim activity structure; distances in km, speeds in km/h, duration in minutes."""
    atype = (a.get("activityType") or {}).get("typeKey")
    distance_km = None
    if a.get("distance") is not None:
        distance_km = round(float(a["distance"]) / 1000.0, 2)
    duration_min = None
    if a.get("duration") is not None:
        duration_min = round(float(a["duration"]) / 60.0, 1)
    avg_speed_kmh = None
    if a.get("averageSpeed") is not None:
        avg_speed_kmh = round(float(a["averageSpeed"]) * 3.6, 2)

    return {
        "activityId": a.get("activityId"),
        "startTimeLocal": a.get("startTimeLocal"),
        "type": atype,
        "name": a.get("activityName"),
        "distance_km": distance_km,
        "duration_min": duration_min,
        "avg_hr": a.get("averageHR"),
        "max_hr": a.get("maxHR"),
        "avg_speed_kmh": avg_speed_kmh,
        "elevation_gain_m": a.get("elevationGain"),
    }


# --- Public fetch functions ---------------------------------------------------
def get_recent_activities(api: Garmin, limit: int = 7) -> List[Dict[str, Any]]:
    """
    Return the most recent activities (normalized).
    """
    try:
        raw = api.get_activities(0, limit) or []
    except GarminConnectTooManyRequestsError as e:
        raise RuntimeError("Rate limited by Garmin (429). Try again later.") from e
    except Exception as e:
        raise RuntimeError(f"Fetching activities failed: {e}") from e

    return [_normalize_activity(a) for a in raw]


def get_vo2max_today(api: Garmin) -> Optional[float]:
    """
    Return today's VO2max (precise if available) or None.
    """
    today = date.today().isoformat()
    try:
        data = api.get_max_metrics(today)  # typically a list with one dict
        if not data:
            return None
        generic = (data[0] or {}).get("generic", {}) or {}
        return generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
    except Exception:
        return None


# --- Sleep via GraphQL (robust to field variations) --------------------------
def _first(*vals, default=None):
    for v in vals:
        if v is not None:
            return v
    return default


def _as_minutes(seconds) -> Optional[float]:
    if seconds is None:
        return None
    try:
        return round(float(seconds) / 60.0, 1)
    except Exception:
        return None


def get_sleep_last_nd(api: Garmin, ndays: int = 7) -> List[Dict[str, Any]]:
    """
    Fetch last N days of sleep via GraphQL sleepSummariesScalar.
    Returns list of dicts: {date, sleepDurationMin, sleepEfficiency, deepSleepMin, lightSleepMin, remSleepMin, awakenings, avgHr}
    Auto-derives total sleep minutes from stage sums if missing.
    """
    if ndays <= 0:
        return []

    end = date.today()
    start = end - timedelta(days=ndays - 1)
    query = {
        "query": (
            f'query{{'
            f'sleepSummariesScalar(startDate:"{start.isoformat()}", endDate:"{end.isoformat()}")'
            f'}}'
        )
    }

    try:
        raw = api.query_garmin_graphql(query) or {}
    except Exception:
        return []

    data = raw.get("data") or raw
    items = data.get("sleepSummariesScalar") or []

    out: List[Dict[str, Any]] = []
    for item in items:
        # common containers
        summary = item.get("summary") or item.get("sleepSummary") or item

        # date
        d = _first(
            item.get("calendarDate"),
            summary.get("calendarDate") if isinstance(summary, dict) else None,
            item.get("date"),
        )

        # durations (seconds)
        dur_sec = _first(
            summary.get("durationInSeconds") if isinstance(summary, dict) else None,
            summary.get("sleepDurationInSeconds") if isinstance(summary, dict) else None,
            item.get("durationInSeconds"),
            item.get("sleepDurationInSeconds"),
        )
        deep_sec = _first(
            summary.get("deepSleepSeconds") if isinstance(summary, dict) else None,
            summary.get("deepSleepDurationInSeconds") if isinstance(summary, dict) else None,
            item.get("deepSleepSeconds"),
            item.get("deepSleepDurationInSeconds"),
        )
        light_sec = _first(
            summary.get("lightSleepSeconds") if isinstance(summary, dict) else None,
            summary.get("lightSleepDurationInSeconds") if isinstance(summary, dict) else None,
            item.get("lightSleepSeconds"),
            item.get("lightSleepDurationInSeconds"),
        )
        rem_sec = _first(
            summary.get("remSleepSeconds") if isinstance(summary, dict) else None,
            summary.get("remSleepDurationInSeconds") if isinstance(summary, dict) else None,
            item.get("remSleepSeconds"),
            item.get("remSleepDurationInSeconds"),
        )

        efficiency = _first(
            summary.get("sleepEfficiency") if isinstance(summary, dict) else None,
            item.get("sleepEfficiency"),
        )
        awakenings = _first(
            summary.get("awakeningsCount") if isinstance(summary, dict) else None,
            summary.get("numberOfAwakenings") if isinstance(summary, dict) else None,
            item.get("awakeningsCount"),
            item.get("numberOfAwakenings"),
        )
        avg_hr = _first(
            summary.get("averageHeartRate") if isinstance(summary, dict) else None,
            item.get("averageHeartRate"),
        )

        row = {
            "date": d,
            "sleepDurationMin": _as_minutes(dur_sec),
            "sleepEfficiency": efficiency,
            "deepSleepMin": _as_minutes(deep_sec),
            "lightSleepMin": _as_minutes(light_sec),
            "remSleepMin": _as_minutes(rem_sec),
            "awakenings": awakenings,
            "avgHr": avg_hr,
        }
        
                # Skip placeholder/empty items (no date and no useful fields)
        if not d and all(
            v is None for v in (
                row["sleepDurationMin"],
                row["deepSleepMin"],
                row["lightSleepMin"],
                row["remSleepMin"],
                row["sleepEfficiency"],
                row["avgHr"],
                row["awakenings"],
            )
        ):
            continue


        # derive total minutes if stages exist but total is missing
        if row["sleepDurationMin"] is None:
            stages = [row.get("deepSleepMin"), row.get("lightSleepMin"), row.get("remSleepMin")]
            stage_sum = sum(v for v in stages if v is not None)
            if stage_sum > 0:
                row["sleepDurationMin"] = round(stage_sum, 1)

        out.append(row)

    # chronological sort
    out.sort(key=lambda x: (x.get("date") or ""))
    return out


# --- Optional demo runner -----------------------------------------------------
def _demo_print(limit: int, sleep_days: int, token_dir: str | Path) -> None:
    api = get_api(token_dir)
    acts = get_recent_activities(api, limit=limit)
    vo2 = get_vo2max_today(api)
    sleep = get_sleep_last_nd(api, ndays=sleep_days)

    print(json.dumps(
        {
            "fetched_at": datetime.now().isoformat(),
            "vo2max": vo2,
            "activities_recent": acts,
            "sleep": sleep,
        },
        ensure_ascii=False,
        indent=2,
    ))


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Garmin lightweight fetch helpers (no DB).")
    p.add_argument("--token-dir", default="~/.garminconnect", help="Token directory (default: ~/.garminconnect)")
    p.add_argument("--limit", type=int, default=7, help="Recent activities to fetch")
    p.add_argument("--sleep-days", type=int, default=7, help="How many past days of sleep to fetch")
    p.add_argument("--demo", action="store_true", help="Print a quick JSON summary (optional)")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    if args.demo:
        try:
            _demo_print(args.limit, args.sleep_days, args.token_dir)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    # Default: no output — import the functions in your app.
