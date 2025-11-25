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
            return jsonify({"error": "User input or row_id is required"}), 400

        # =========================================================
        # MODE 2: FETCH STATUS (The polling request from the client)
        # =========================================================
        if row_id_to_fetch:
            try:
                # FIX 1: Explicitly request the output columns.
                # Without 'columns', the SDK often returns only input/metadata.
                # We also assume 'decoded_tags' is a column name in your Action Table.
                row_response = jamai.table.get_table_row(
                    p.TableType.ACTION,
                    TABLE_ID,
                    row_id_to_fetch,
                    columns=["route_analysis", "selected_pps", "decoded_tags"]
                )
                
                # FIX 2: Handle Response as an Object (Dot Notation)
                # The SDK returns a Pydantic model, so we access .row instead of ["row"]
                row_data = row_response.row 

                # FIX 3: Check for completion
                # We check if the 'route_analysis' cell has a non-empty 'value'.
                # Note: We use .get() on the row dictionary, then access .value on the cell object.
                route_analysis_cell = row_data.get("route_analysis")
                selected_pps_cell = row_data.get("selected_pps")
                decoded_tags_cell = row_data.get("decoded_tags")

                if (route_analysis_cell and route_analysis_cell.value and 
                    selected_pps_cell and selected_pps_cell.value):
                    
                    return jsonify({
                        "success": True,
                        "status": "complete",
                        "analysis": route_analysis_cell.value,
                        # Handle tags safely if the column is empty/missing
                        "tags": decoded_tags_cell.value if decoded_tags_cell else "",
                        "selected_pps": selected_pps_cell.value
                    }), 200
                
                # If values are missing/empty, it's still processing
                return jsonify({
                    "success": False, 
                    "status": "pending", 
                    "row_id": row_id_to_fetch
                }), 200

            except Exception as e:
                # Catch specific fetching errors (e.g. row not found yet)
                print(f"Polling check error: {e}")
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
                "user_input": user_input,
                "location_details": location_details,
                # "created_at": datetime.now().isoformat() # Optional: Add if your table expects it
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

            # Return job ID immediately so client can start polling
            return jsonify({
                "success": True, 
                "status": "submitted", 
                "row_id": row_id
            }), 200

    except Exception as e:
        print(f"FATAL ERROR in analyze_route: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)