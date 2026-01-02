# render_prompt.py
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# --- Jinja ---
from jinja2 import Environment, FileSystemLoader, select_autoescape

# --- Your Garmin helpers (unchanged) ---
from garmin import get_api, get_recent_activities, get_vo2max_today, get_sleep_last_nd

from your_data import ctx as base_ctx
try:
    from my_data import ctx as private_ctx
    ctx = private_ctx  # override if present
except ImportError:
    ctx = base_ctx


DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "planner.sqlite")

def _fmt_workout_line(day_idx: int, w: dict) -> str:
    """
    Build a compact line like:
    "Mo: Run/Walk Intervall 30' sehr locker (RPE 3) — 5' gehen; 10×(1' laufen / 2' gehen); 5' gehen"
    """
    day = DAYS[day_idx] if 0 <= day_idx < 7 else "?"
    title = (w.get("title") or "").strip()
    duration = f"{int(w['duration_min'])}'" if w.get("duration_min") else ""
    intensity = (w.get("intensity") or "").strip()

    # Compose main part
    parts = [title]
    if duration:
        parts.append(duration)
    if intensity:
        parts.append(intensity)
    main = " ".join([p for p in parts if p])

    notes = (w.get("notes") or "").strip()
    suffix = f" — {notes}" if notes else ""

    # Optionally show up to 3 exercise names for strength
    ex_names = []
    for ex in (w.get("exercises") or []):
        nm = (ex.get("name") or "").strip()
        if nm:
            ex_names.append(nm)
    if w.get("wtype") == "strength" and ex_names:
        ex_txt = ", ".join(ex_names[:3]) + ("…" if len(ex_names) > 3 else "")
        suffix = (suffix + " ") if suffix else " "
        suffix += f"(Ex: {ex_txt})"

    line_body = main if main else w.get("wtype", "Training")
    return f"{day}: {line_body}{suffix}"

def _fetch_plan_via_api() -> list[str] | None:
    """Try to fetch workouts via Flask API: /api/workouts"""
    if not PLANNER_API_BASE:
        return None
    import json
    import urllib.request
    url = f"{PLANNER_API_BASE}/api/workouts"
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    # Group and order
    by_day = {i: [] for i in range(7)}
    for w in data:
        by_day[int(w.get("day", 0))].append(w)
    for d in by_day:
        by_day[d].sort(key=lambda x: int(x.get("position", 0)))

    lines = []
    for d in range(7):
        for w in by_day[d]:
            lines.append(_fmt_workout_line(d, w))
    return lines

def _fetch_plan_via_sqlite() -> list[str] | None:
    """Read directly from planner.sqlite if present, including a few exercise names."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Pull workouts ordered by day, position
        cur.execute("""
            SELECT id, day, position, wtype, title, duration_min, intensity, notes
            FROM workouts
            ORDER BY day ASC, position ASC
        """)
        workouts = [dict(row) for row in cur.fetchall()]

        # Pull exercises for those workouts (optional)
        ids = [w["id"] for w in workouts]
        ex_by_w = {wid: [] for wid in ids}
        if ids:
            qmarks = ",".join("?" for _ in ids)
            cur.execute(f"""
                SELECT we.workout_id, ec.name
                FROM workout_exercises we
                JOIN exercise_catalog ec ON ec.id = we.exercise_id
                WHERE we.workout_id IN ({qmarks})
                ORDER BY we.workout_id ASC, we.id ASC
            """, ids)
            for row in cur.fetchall():
                ex_by_w[row["workout_id"]].append({"name": row["name"]})

        lines = []
        for w in workouts:
            w["exercises"] = ex_by_w.get(w["id"], [])
            lines.append(_fmt_workout_line(int(w.get("day", 0)), w))

        conn.close()
        return lines
    except Exception:
        return None

def build_plan_lines() -> list[str]:
    """
    Try API first, then SQLite. If both fail, return a safe static fallback.
    """
    lines = _fetch_plan_via_sqlite()
    if lines:
        return lines
      
    raise Exception('Did not find your plan')

# ---------------- Garmin fetch (unchanged) ----------------
api = get_api()
acts = get_recent_activities(api, limit=30)
vo2 = get_vo2max_today(api)
sleep = get_sleep_last_nd(api, ndays=7)

# ---------------- Build ctx ----------------
week_label = f"KW{datetime.now().isocalendar().week:02d}"
plan_days = build_plan_lines()

ctx["meta"]["now_iso"] = datetime.now().isoformat()

ctx["plan"] = {
    "week_label": week_label,
    "days": plan_days
}

ctx["garmin"] = {
    "vo2max": {"latest": vo2, "trend": "steigend"},
    "sleep": {
        "avg_score": round(sum([d.get("sleepEfficiency") or 0 for d in sleep]) / len(sleep), 1) if sleep else None,
        "avg_duration_h": round(
            sum([(d.get("sleepDurationMin") or 0) for d in sleep]) / len(sleep) / 60, 2
        ) if sleep else None,
        "avg_rhr": None
    },
    "activities": [
        {
            "date": a.get("startTimeLocal","")[:10],
            "type": a.get("type"),
            "title": a.get("name"),
            "duration_min": a.get("duration_min"),
            "distance_km": a.get("distance_km"),
            "avg_hr": a.get("avg_hr")
        } for a in (acts or [])
    ],
    "flags": {"cycling_hr_maybe_inaccurate": True}
}

# ---------------- Render Jinja template ----------------
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(disabled_extensions=("j2", "txt"))
)
tpl = env.get_template("new_prompt.j2")
prompt = tpl.render(**ctx)

print(prompt)
Path("prompt_out.txt").write_text(prompt, encoding="utf-8")
