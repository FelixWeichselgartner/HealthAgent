import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "planner.sqlite")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------- Models ----------

class ExerciseCatalog(db.Model):
    __tablename__ = "exercise_catalog"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    video_url = db.Column(db.String, nullable=True)

class Workout(db.Model):
    __tablename__ = "workouts"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False, default=0)  # 0=Mo ... 6=So
    position = db.Column(db.Integer, nullable=False, default=0)  # order within day
    wtype = db.Column(db.String, nullable=False)  # 'strength' | 'cardio' | 'golf' | 'other'
    title = db.Column(db.String, nullable=False)
    # cardio
    duration_min = db.Column(db.Integer, nullable=True)
    intensity = db.Column(db.String, nullable=True)  # e.g., 'RPE 3', 'locker'
    # notes for all
    notes = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exercises = relationship("WorkoutExercise", backref="workout", cascade="all, delete-orphan")

class WorkoutExercise(db.Model):
    __tablename__ = "workout_exercises"
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise_catalog.id"), nullable=False)
    sets = db.Column(db.Integer, nullable=False, default=3)
    reps = db.Column(db.Integer, nullable=False, default=10)
    exercise = relationship("ExerciseCatalog")

# ---------- Helpers ----------

DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

def day_name_to_index(name: str) -> int:
    name = name.strip().lower()
    mapping = {
        "mo":0,"montag":0,
        "di":1,"dienstag":1,
        "mi":2,"mittwoch":2,
        "do":3,"donnerstag":3,
        "fr":4,"freitag":4,
        "sa":5,"samstag":5,
        "so":6,"sonntag":6
    }
    return mapping.get(name, 0)

# ---------- Routes (Pages) ----------

@app.route("/")
def index():
    # Workouts gruppieren (unverändert)
    data = {i: [] for i in range(7)}
    workouts = Workout.query.order_by(Workout.day.asc(), Workout.position.asc()).all()
    for w in workouts:
        data[w.day].append(w)

    # Übungen in dicts serialisieren (NEU)
    exercises = ExerciseCatalog.query.order_by(ExerciseCatalog.name.asc()).all()
    exercises_js = [
        {"id": e.id, "name": e.name, "video_url": e.video_url or ""}
        for e in exercises
    ]

    return render_template("index.html", days=DAYS, plan=data, exercises=exercises_js)


# ---------- API (for Agent + UI) ----------

@app.route("/api/workouts", methods=["GET"])
def api_list_workouts():
    workouts = Workout.query.order_by(Workout.day.asc(), Workout.position.asc()).all()
    def w_to_dict(w):
        return {
            "id": w.id,
            "day": w.day,
            "position": w.position,
            "wtype": w.wtype,
            "title": w.title,
            "duration_min": w.duration_min,
            "intensity": w.intensity,
            "notes": w.notes,
            "exercises": [
                {
                    "id": we.id,
                    "exercise_id": we.exercise_id,
                    "name": we.exercise.name if we.exercise else "",
                    "video_url": we.exercise.video_url if we.exercise else "",
                    "sets": we.sets,
                    "reps": we.reps,
                }
                for we in w.exercises
            ],
        }
    return jsonify([w_to_dict(w) for w in workouts])

@app.route("/api/workouts", methods=["POST"])
def api_create_workout():
    data = request.json or {}
    w = Workout(
        day=int(data.get("day", 0)),
        position=int(data.get("position", 0)),
        wtype=data.get("wtype","other"),
        title=data.get("title","Training"),
        duration_min=data.get("duration_min"),
        intensity=data.get("intensity"),
        notes=data.get("notes")
    )
    db.session.add(w)
    db.session.commit()
    return jsonify({"id": w.id}), 201

@app.route("/api/workout/<int:w_id>", methods=["PATCH"])
def api_update_workout(w_id):
    w = Workout.query.get_or_404(w_id)
    data = request.json or {}
    # generic fields
    for field in ["day","position","wtype","title","duration_min","intensity","notes"]:
        if field in data:
            setattr(w, field, data[field] if field not in ["day","position"] else int(data[field]))
    db.session.commit()
    return jsonify({"status":"ok"})

@app.route("/api/workout/<int:w_id>", methods=["DELETE"])
def api_delete_workout(w_id):
    w = Workout.query.get_or_404(w_id)
    db.session.delete(w)
    db.session.commit()
    return jsonify({"status":"deleted"})

@app.route("/api/workout/<int:w_id>/exercises", methods=["PUT"])
def api_replace_exercises(w_id):
    w = Workout.query.get_or_404(w_id)
    data = request.json or {}
    # data format: [{"exercise_id":1,"sets":3,"reps":12}, ...]
    # Replace all
    for existing in list(w.exercises):
        db.session.delete(existing)
    for e in data.get("exercises", []):
        item = WorkoutExercise(
            workout_id=w.id,
            exercise_id=int(e["exercise_id"]),
            sets=int(e.get("sets",3)),
            reps=int(e.get("reps",10))
        )
        db.session.add(item)
    db.session.commit()
    return jsonify({"status":"ok"})

@app.route("/api/reorder", methods=["POST"])
def api_reorder():
    """
    Payload: {"day": 0-6, "order": [workout_id_in_order]}
    """
    data = request.json or {}
    day = int(data["day"])
    order = data.get("order", [])
    for idx, wid in enumerate(order):
        w = Workout.query.get(int(wid))
        if w:
            w.day = day
            w.position = idx
    db.session.commit()
    return jsonify({"status":"ok"})

@app.route("/api/exercises", methods=["GET"])
def api_exercises():
    items = ExerciseCatalog.query.order_by(ExerciseCatalog.name.asc()).all()
    return jsonify([{"id":e.id,"name":e.name,"video_url":e.video_url} for e in items])

# ---------- Seed / Init ----------

@app.route("/init")
def init_db():
    db.drop_all()
    db.create_all()

    # Exercise catalog (mit deinen YouTube-Links)
    calf_raise = ExerciseCatalog(name="Wadenheben", video_url="https://youtube.com/shorts/xr_bZ3hu_YI?si=b_J5rnAbs4c6_woI")
    bird_dog = ExerciseCatalog(name="Bird Dog", video_url="https://youtube.com/shorts/Yap7kqAFHYo?si=dukxl34nlcIHcWwM")
    clamshell = ExerciseCatalog(name="Clamshells", video_url="")
    monster_walks = ExerciseCatalog(name="Monster Walks (Miniband)", video_url="")
    spanish_squat = ExerciseCatalog(name="Spanish Squat", video_url="")
    step_down = ExerciseCatalog(name="Step-Down (10–15 cm)", video_url="")
    side_plank = ExerciseCatalog(name="Side Plank", video_url="")
    db.session.add_all([calf_raise, bird_dog, clamshell, monster_walks, spanish_squat, step_down, side_plank])
    db.session.commit()

    # Muster-Plan (Woche 1 Regeneration)
    # Mo – Kraft & Physio
    w_mo = Workout(day=0, position=0, wtype="strength", title="Kraft & Physio (30–35 min)", notes="Langsam, exzentrisch 3s")
    db.session.add(w_mo); db.session.commit()
    def add_ex(w, ex_name, sets, reps):
        ex = ExerciseCatalog.query.filter_by(name=ex_name).first()
        if ex:
            db.session.add(WorkoutExercise(workout_id=w.id, exercise_id=ex.id, sets=sets, reps=reps))
            db.session.commit()

    add_ex(w_mo, "Glute Bridge", 3, 12)  # Hinweis: nicht im Katalog? -> optional
    add_ex(w_mo, "Clamshells", 3, 12)
    add_ex(w_mo, "Monster Walks (Miniband)", 3, 12)
    add_ex(w_mo, "Spanish Squat", 3, 10)
    add_ex(w_mo, "Step-Down (10–15 cm)", 3, 8)
    add_ex(w_mo, "Side Plank", 3, 1)  # 1 Satz = 30–40s/Seite (Info in Notes)

    # Di – Run/Walk
    w_di = Workout(day=1, position=0, wtype="cardio", title="Run/Walk Intervall",
                   duration_min=30, intensity="sehr locker (RPE 3)",
                   notes="5' gehen; 10×(1' laufen / 2' gehen); 5' gehen; Tempo 6:10–6:45/km")
    db.session.add(w_di)

    # Mi – Mobility + leichtes Kraft
    w_mi = Workout(day=2, position=0, wtype="strength", title="Mobility + leichtes Kraft (25–30 min)",
                   notes="Hüftabduktion 3×12, Wadenheben 3×15, Dead Bug 3×10/Seite; 10–15' Gehen")
    db.session.add(w_mi); db.session.commit()
    add_ex(w_mi, "Wadenheben", 3, 15)
    add_ex(w_mi, "Bird Dog", 3, 10)

    # Do – Rad locker
    w_do = Workout(day=3, position=0, wtype="cardio", title="Rad locker",
                   duration_min=40, intensity="RPE 3",
                   notes="TF 85–95 rpm, flach, kein Druck")
    db.session.add(w_do)

    # Fr – Run/Walk Progression
    w_fr = Workout(day=4, position=0, wtype="cardio", title="Run/Walk Progression",
                   duration_min=32, intensity="RPE 3–4",
                   notes="5' gehen; 8×(2' laufen / 2' gehen); 5' gehen")
    db.session.add(w_fr)

    # Sa – Regeneration
    w_sa = Workout(day=5, position=0, wtype="other", title="Regeneration",
                   duration_min=40, intensity="sehr locker",
                   notes="Spaziergang 30–40', Dehnen/Release 10–15'")
    db.session.add(w_sa)

    # So – Golf 9 Loch (+ optional cardio)
    w_so = Workout(day=6, position=0, wtype="other", title="Golf (9 Loch)",
                   notes="Warm-up 3–5'; optional 20–25' locker joggen oder 30–40' Recovery-Rad (nur schmerzfrei)")
    db.session.add(w_so)

    db.session.commit()
    return "DB initialisiert & Musterplan angelegt. Gehe auf /"

# ---------- Main ----------

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        with app.app_context():
            db.create_all()
    app.run(debug=True)
