from flask import Flask, request, jsonify
from jamaibase import JamAI, protocol as p
import os
import time
import uuid
from datetime import datetime

app = Flask(__name__)

# 1. Configuration
# Ensure these are set in your Vercel Environment Variables
PROJECT_ID = os.getenv("JAMAI_PROJECT_ID")
API_URL = os.getenv("JAMAI_API_URL")
API_KEY = os.getenv("JAMAI_PAT")
TABLE_ID = os.getenv("ACTION_TABLE_ID")

# Initialize JamAI Client
jamai = JamAI(
    project_id=PROJECT_ID, 
    api_key=API_KEY, 
    base_url=API_URL
)

@app.route('/api/analyze', methods=['POST'])
def analyze_route():
    try:
        data = request.json
        user_input = data.get('user_input')
        location_details = data.get('location_details') # e.g., "Lat: 3.1, Long: 101.6"
        
        if not user_input:
            return jsonify({"error": "User input is required"}), 400

        # 2. Add Row to JamAI Action Table
        # We insert the inputs. The LLM columns (decoded_tags, route_analysis) are generated automatically.
        row_data = {
            "action": "find_safe_shelter",
            "user_input": user_input,
            "location_details": location_details,
            "created_at": datetime.now().isoformat()
        }

        # Using the SDK to add the row
        completion = jamai.table.add_table_rows(
            table_type=p.TableType.action,
            table_id=TABLE_ID,
            rows=[row_data],
            stream=False
        )
        
        if not completion.rows:
             return jsonify({"error": "Failed to add row to JamAI"}), 500

        row_id = completion.rows[0].row_id

        # 3. Poll for LLM Completion (RAG Analysis)
        # Since Gen Tables are asynchronous, we wait briefly for the 'route_analysis' to populate.
        # In a production app, you might use WebSockets or client-side polling.
        attempts = 0
        max_retries = 10
        final_row = None

        while attempts < max_retries:
            # Fetch the specific row to check if LLM has finished
            row_response = jamai.table.get_table_row(
                table_type=p.TableType.action,
                table_id=TABLE_ID,
                row_id=row_id
            )
            
            # Check if the LLM output column is not null/empty
            # Note: Adjust 'route_analysis' key if your column ID differs slightly
            if row_response.row and row_response.row.get("route_analysis"):
                final_row = row_response.row
                break
            
            time.sleep(1.5) # Wait 1.5 seconds before retry
            attempts += 1

        if not final_row:
            return jsonify({"message": "Analysis in progress. Please check back.", "row_id": row_id}), 202

        # 4. Return the Intelligence
        return jsonify({
            "success": True,
            "analysis": final_row.get("route_analysis"),
            "tags": final_row.get("decoded_tags")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=3000)