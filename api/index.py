from flask import Flask, request, jsonify
from datetime import datetime
from jamaibase import JamAI, types as p
import os
import sys # Import sys to force flush logs to Vercel console

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
        row_id_to_fetch = data.get('row_id') 

        if not user_input and not row_id_to_fetch:
            return jsonify({"error": "User input or row_id is required"}), 400

        # =========================================================
        # MODE 2: FETCH STATUS (Polling)
        # =========================================================
        if row_id_to_fetch:
            print(f"DEBUG: Fetching Row ID: {row_id_to_fetch}", file=sys.stderr)
            
            try:
                # 1. Fetch the row
                row_response = jamai.table.get_table_row(
                    p.TableType.ACTION,
                    TABLE_ID,
                    row_id_to_fetch,
                    columns=["route_analysis", "selected_pps", "decoded_tags"]
                )
                
                # 2. Extract the row data safely
                # If it's a Pydantic object, .row might be a dict or object. 
                # We handle both by trying to convert or access directly.
                row_data = row_response.row
                
                # Helper function to handle Dict vs Object ambiguity
                def get_cell_val(data_row, key):
                    # Step 1: Get the cell (Dict get or Object attribute)
                    if isinstance(data_row, dict):
                        cell = data_row.get(key)
                    else:
                        cell = getattr(data_row, key, None)
                    
                    if not cell: return None

                    # Step 2: Get the value inside the cell
                    # JamAI cells are usually dicts like {'value': '...'} or objects with .value
                    if isinstance(cell, dict):
                        return cell.get("value")
                    else:
                        return getattr(cell, "value", None)

                # 3. Retrieve values using the helper
                analysis_text = get_cell_val(row_data, "route_analysis")
                pps_text = get_cell_val(row_data, "selected_pps")
                tags_text = get_cell_val(row_data, "decoded_tags")

                print(f"DEBUG: Data Found? Analysis: {bool(analysis_text)}, PPS: {bool(pps_text)}", file=sys.stderr)

                # 4. Check completion
                if analysis_text and pps_text:
                    return jsonify({
                        "success": True,
                        "status": "complete",
                        "analysis": analysis_text,
                        "tags": tags_text if tags_text else "",
                        "selected_pps": pps_text
                    }), 200
                
                # If we are here, data is missing or empty
                return jsonify({
                    "success": False, 
                    "status": "pending", 
                    "row_id": row_id_to_fetch
                }), 200

            except Exception as e:
                # PRINT THE ACTUAL ERROR to Vercel logs
                print(f"ERROR in polling loop: {e}", file=sys.stderr)
                return jsonify({
                    "success": False, 
                    "status": "pending", 
                    "error_details": str(e), # Send error to frontend for inspection
                    "row_id": row_id_to_fetch
                }), 200

        # =========================================================
        # MODE 1: SUBMIT JOB
        # =========================================================
        else:
            print("DEBUG: Submitting new job...", file=sys.stderr)
            
            # RESTORED: 'action' and 'created_at'
            row_data = {
                "action": "find_safe_shelter",       # Tells JamAI which prompt/skill to use
                "user_input": user_input,
                "location_details": location_details,
                "created_at": datetime.now().isoformat() # Timestamps the request
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
                 return jsonify({"error": "Failed to submit job"}), 500

            row_id = completion.rows[0].row_id
            print(f"DEBUG: Job Submitted. Row ID: {row_id}", file=sys.stderr)

            return jsonify({
                "success": True, 
                "status": "submitted", 
                "row_id": row_id
            }), 200

    except Exception as e:
        print(f"FATAL ERROR in analyze_route: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)