# empty_ctx.py
from datetime import datetime

ctx = {
    "meta": {
        "now_iso": datetime.now().isoformat(),
        "timezone": "Europe/Berlin",
        "units": "metric"
    },

    "athlete": {
        "name": "",
        "age": None,
        "weight_kg": None,
        "height_cm": None,
        "training_age_years": None,
        "equipment": {
            "hr_strap": None,
            "treadmill": None,
            "indoor_bike": None
        }
    },

    "goals": {
        "primary": "",
        "secondary": []
    },

    "event": {
        "name": "",
        "date_iso": "",
        "distance_km": None
    },

    "availability": {
        "weekly_time_budget_min": None,
        "cannot_train_days": [],
        "preferred_golf_day": None
    },

    "injury": {
        "phase": "",
        "physio_notes": "",
        "constraints": {
            "max_run_sessions_per_week": None,
            "run_progression_rule": "",
            "no_back_to_back_intensity": None
        }
    },

    "plan": {
        "week_label": "",
        "days": []   # <- fill with list of strings, example: ["Mo: ...", "Di: ..."]
    },

    "diet": {
        "total_protein_g": None,
        "protein_distribution_g": [],
        "supplements": {},
        "notes": ""
    },

    "last_eval": {
        "summary": "",
        "recommendations": ""
    },

    "garmin": {
        "vo2max": {
            "latest": None,
            "trend": ""
        },
        "sleep": {
            "avg_score": None,
            "avg_duration_h": None,
            "avg_rhr": None
        },
        "activities": [],
        "flags": {}
    },

    "compliance": {
        "completion_pct": None,
        "pain_peak": None,
        "doms_level": "",
        "subjective_fatigue": ""
    }
}
