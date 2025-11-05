# Health Agent

This project generates a personalized weekly training & wellness prompt by combining:
- Your saved training plan (from the planner web app / SQLite database)
- Garmin activity, sleep, and VO2max data
- Personal goals, injury constraints, and availability

The output is rendered through a Jinja2 template and can be used as an input prompt for a coaching AI.

## Quick Start

1. Install requirements:
```
pip install -r requirements.txt
```
2. Initialize the training planner database:
```
python app.py
# then open http://127.0.0.1:5000/init
```
3. Customize your personal data in `ctx_private.py` (not included in this repo).
4. Generate your weekly training prompt:
```
python render_prompt.py
```
This will output a text file: `prompt_out.txt`

## Folder Structure

```
.
├─ app.py              # Web UI to edit your training plan
├─ planner.sqlite      # Training plan database
├─ render_prompt.py    # Generates the personalized training prompt
├─ templates/
│   └─ new_prompt.j2   # Jinja2 template for the prompt
└─ empty_ctx.py        # Public, non-sensitive configuration template
```

## Notes
- Never commit your personal data. Keep it in `ctx_private.py` and add it to `.gitignore`.
- If the Flask app is running, `render_prompt.py` fetches workouts from the live API.
  If not, it reads directly from `planner.sqlite`.
