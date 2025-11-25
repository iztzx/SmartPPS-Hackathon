import os
import json
from flask import Flask, request, jsonify
from jamaibase import JamAI, types as t

# Env mapping:
# JAMAI_PROJECT_ID -> project_id
# JAMAI_PAT        -> token
# JAMAI_API_URL    -> api_base (SDK also supports env JAMAI_API_BASE; passing explicit arg is fine)
JAMAI_PROJECT_ID = os.environ.get("JAMAI_PROJECT_ID", "")
JAMAI_PAT = os.environ.get("JAMAI_PAT", "")
JAMAI_API_URL = os.environ.get("JAMAI_API_URL", "")

# Initialize JamAI client (explicit api_base for compatibility)
jamai = JamAI(project_id=JAMAI_PROJECT_ID, token=JAMAI_PAT, api_base=JAMAI_API_URL)

app = Flask(__name__)

# Assumptions:
# - Action table schema exists with columns:
#   action, user_input, location_details, decoded_tags (LLM), route_analysis (LLM), created_at
# - Knowledge table (e.g., "pps-knowledge") contains PPS listings with embeddings for RAG.
# - The action table's LLM column gen_config includes a prompt that:
#   1) Retrieves 3 nearest PPS from the knowledge table
#   2) Evaluates constraints (stairs vs. bedridden, pet policy, OKU facilities)
#   3) Produces route_analysis and structured hints for markers.
#
# You can change ACTION_TABLE_ID and KT_ID to match your project.
ACTION_TABLE_ID = os.environ.get("ACTION_TABLE_ID", "action-routing")
KT_ID = os.environ.get("KT_ID", "pps-knowledge")

def _fallback_route_logic(user_input: str, location_details: str):
    """
    Local fallback if JamAI API is unreachable: emulate the sample reasoning.
    """
    # Mocked PPS options for demo
    pps = [
        {"name": "SK Gombak", "distance": 1, "notes": "2nd floor classrooms only", "rules": []},
        {"name": "Dewan Serbaguna", "distance": 2, "notes": "Hall", "rules": ["No Animals"]},
        {"name": "Kolej Komuniti", "distance": 4, "notes": "OKU toilets + outdoor pet area", "rules": ["Pets outdoors OK"]},
    ]
    has_bedridden = "bedridden" in user_input.lower() or "warga emas" in user_input.lower()
    has_cat = "cat" in user_input.lower()

    decisions = []
    for p in pps:
        if p["name"] == "SK Gombak" and has_bedridden:
            decisions.append({"name": p["name"], "distance": p["distance"], "suitability": "Not Suitable", "reason": "Grandmother cannot climb stairs."})
        elif p["name"] == "Dewan Serbaguna" and has_cat:
            decisions.append({"name": p["name"], "distance": p["distance"], "suitability": "Not Suitable", "reason": "Pet policy: No Animals."})
        elif p["name"] == "Kolej Komuniti":
            decisions.append({"name": p["name"], "distance": p["distance"], "suitability": "Best Match", "reason": "OKU toilets + designated outdoor pet area."})
        else:
            decisions.append({"name": p["name"], "distance": p["distance"], "suitability": "Unknown", "reason": ""})

    best = next((d for d in decisions if d["suitability"] == "Best Match"), None)
    analysis_lines = [
        f"Input: {user_input}",
        f"Location: {location_details}",
        "Find nearest PPS:",
        f"- A (1km): SK Gombak -> 2nd floor classrooms only. Rejection: bedridden cannot climb stairs.",
        f"- B (2km): Dewan Serbaguna -> Pet Policy: Strict No Animals. Rejection: user has a cat.",
        f"- C (4km): Kolej Komuniti -> OKU toilets + outdoor pet area. Selection: Recommended.",
        f"Recommendation: {best['name'] if best else 'None'}"
    ]
    return {
        "route_analysis": "\n".join(analysis_lines),
        "markers": decisions
    }

@app.route("/api/route", methods=["POST"])
def route():
    payload = request.get_json(force=True)
    user_input = (payload.get("user_input") or "").strip()
    location_details = (payload.get("location_details") or "").strip()
    created_at = (payload.get("created_at") or "").strip()

    # Add row to Action table so LLM can produce decoded_tags + route_analysis with RAG refs
    try:
        completion = jamai.table.add_table_rows(
            "action",
            t.MultiRowAddRequest(
                table_id=ACTION_TABLE_ID,
                data=[{
                    "action": "family_first_route",
                    "user_input": user_input,
                    "location_details": location_details,
                    "created_at": created_at
                }],
                stream=False
            ),
        )
        # Extract generated outputs from SDK response
        row = completion.rows[0].columns
        route_analysis = row.get("route_analysis").text if "route_analysis" in row else ""
        decoded_tags = row.get("decoded_tags").text if "decoded_tags" in row else ""

        # Optional: parse hints for markers from route_analysis or decoded_tags
        # For demo, we derive simple markers by pattern checks.
        markers = []
        lower = (route_analysis or "").lower() + " " + (decoded_tags or "").lower()
        def has(tok): return tok in lower
        markers.append({"name": "SK Gombak", "distance": 1, "suitability": "Not Suitable" if has("stairs") or has("2nd floor") or has("bedridden") else "Unknown"})
        markers.append({"name": "Dewan Serbaguna", "distance": 2, "suitability": "Not Suitable" if has("no animals") or has("strict no animals") or has("pet policy") else "Unknown"})
        markers.append({"name": "Kolej Komuniti", "distance": 4, "suitability": "Best Match" if has("oku") or has("outdoor pet area") or has("designated pet") else "Unknown"})

        return jsonify({
            "route_analysis": route_analysis,
            "decoded_tags": decoded_tags,
            "markers": markers
        })
    except Exception:
        # Local fallback for resilience
        data = _fallback_route_logic(user_input, location_details)
        return jsonify(data), 200

# Optional: health check
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

# For local testing: run flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
