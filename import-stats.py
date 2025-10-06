import json
from datetime import datetime, timedelta

DATA_FILE = "sessions.json"
USER_ID = 1395851154327343155
USER_NAME = "terter08255"
N_SESSIONS = 54
TOTAL_RESULT = 31940
TOTAL_HOURS = 4.5*54

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

per_session_result = TOTAL_RESULT / N_SESSIONS
per_session_hours = TOTAL_HOURS / N_SESSIONS
start_date = datetime(2024, 6, 1)

for i in range(N_SESSIONS):
    session = {
        "user_id": USER_ID,
        "user_name": USER_NAME,
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
        "date": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
        "lieu": "Ancienne période",
        "resultat": f"{per_session_result:.2f}",
        "buyin": "0",
        "heures": f"{per_session_hours:.1f}",
        "plan_respecte": "n/a",
        "tilt": "n/a",
        "main_cle": "",
        "erreur": "0",
        "call_muck": "0",
        "patience": "n/a",
        "points_positifs": "",
        "action_corrective": ""
    }
    data.append(session)

with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"{N_SESSIONS} anciennes sessions ajoutées pour {USER_NAME}")
