from flask import Flask, request, jsonify
from jamaibase import JamAI, types as p
import os
from datetime import datetime

app = Flask(__name__)

# 1. Configuration
PROJECT_ID = os.getenv("JAMAI_PROJECT_ID")
API_KEY = os.getenv("JAMAI_PAT")
TABLE_ID = os.getenv("ACTION_TABLE_ID")

# Initialize JamAI Client
jamai = JamAI(
    project_id=PROJECT_ID, 
    token=API_KEY 
)

@app.route('/api/analyze', methods=['POST'])
def analyze_route():
    try:
        data = request.json
        user_input = data.get('user_input')
        location_details = data.get('location_details')
        row_id_to_fetch = data.get('row_id') # Key for polling request

        if not user_input and not row_id_to_fetch:
            return jsonify({"error": "User input is required"}), 400

        # =========================================================
        # MODE 2: FETCH STATUS (The polling request from the client)
        # =========================================================
        if row_id_to_fetch:
            # FIX 1: Get the row using positional arguments
            row_response = jamai.table.get_table_row(
                p.TableType.ACTION,
                TABLE_ID,
                row_id_to_fetch
            )
            
            # Extract the nested 'row' dictionary safely
            final_row = row_response.get("row")

            if final_row:
                
                # FIX 2: Check for completion by looking for non-empty content in the inner ["value"] key
                if (final_row.get("route_analysis", {}).get("value") and 
                    final_row.get("selected_pps", {}).get("value")):
                    
                    # FIX 3: Extract the final output using the ["value"] key
                    return jsonify({
                        "success": True,
                        "status": "complete",
                        "analysis": final_row["route_analysis"]["value"], 
                        "tags": final_row.get("decoded_tags", {}).get("value"),
                        "selected_pps": final_row["selected_pps"]["value"]
                    }), 200
            
            # If the row is not yet available or analysis is still running
            return jsonify({
                "success": False, 
                "status": "pending", 
                "row_id": row_id_to_fetch
            }), 200

        # =========================================================
        # MODE 1: SUBMIT JOB (The initial request)
        # =========================================================
        else:
            row_data = {
                "action": "find_safe_shelter",
                "user_input": user_input,
                "location_details": location_details,
                "created_at": datetime.now().isoformat()
            }
            
            add_request = p.MultiRowAddRequest(
                table_id=TABLE_ID,
                data=[row_data],
                stream=False,
            )

            completion = jamai.table.add_table_rows(
                table_type=p.TableType.ACTION,
                request=add_request,
            )
            
            if not completion.rows:
                 return jsonify({"error": "Failed to submit job to JamAI"}), 500

            row_id = completion.rows[0].row_id

            # Return job ID immediately (fast response)
            return jsonify({
                "success": True, 
                "status": "submitted", 
                "row_id": row_id
            }), 200

    except Exception as e:
        print(f"FATAL ERROR in analyze_route: {e}")
        return jsonify({"error": str(e)}), 500