from flask import Flask, request, jsonify
from jamaibase import JamAI, types as p
import os
import time
from datetime import datetime

app = Flask(__name__)

# 1. Configuration
PROJECT_ID = os.getenv("JAMAI_PROJECT_ID")
API_URL = os.getenv("JAMAI_API_URL")
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
        
        if not user_input:
            return jsonify({"error": "User input is required"}), 400

        # 2. Add Row to JamAI Action Table
        row_data = {
            "action": "find_safe_shelter",
            "user_input": user_input,
            "location_details": location_details,
            "created_at": datetime.now().isoformat()
        }
        
        # Uses p.MultiRowAddRequest 
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
             return jsonify({"error": "Failed to add row to JamAI"}), 500

        row_id = completion.rows[0].row_id

        # 3. Poll for LLM Completion (RAG Analysis)
        attempts = 0
        max_retries = 20  # <<< FIX: Increased polling attempts to 20 (30 seconds total wait)
        final_row = None

        while attempts < max_retries:
            
            # get_table_row uses positional arguments (table_type, table_id, row_id)
            row_response = jamai.table.get_table_row(
                p.TableType.ACTION,
                TABLE_ID,
                row_id
            )
            
            # Check for the existence of the required columns
            if (row_response.get("row") and 
                row_response["row"].get("route_analysis") and 
                row_response["row"].get("selected_pps")):
                
                final_row = row_response["row"]
                break
            
            time.sleep(1.5)
            attempts += 1

        if not final_row:
            return jsonify({"message": "Analysis in progress. Please check back.", "row_id": row_id}), 202

        # 4. Return the Intelligence
        return jsonify({
            "success": True,
            "analysis": final_row.get("route_analysis"),
            "tags": final_row.get("decoded_tags"),
            "selected_pps": final_row.get("selected_pps")
        })

    except Exception as e:
        print(f"FATAL ERROR in analyze_route: {e}")
        return jsonify({"error": str(e)}), 500

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=3000)