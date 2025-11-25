from flask import Flask, request, jsonify
from jamaibase import JamAI, types as p
import os
import sys
import re
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
                
                # 2. INTELLIGENT DATA EXTRACTION (Fixes "Row data is empty")
                row_data = None
                
                # Case A: Response is a Dict
                if isinstance(row_response, dict):
                    # Debug: Print keys to see what we actually got
                    print(f"DEBUG: Response Keys: {list(row_response.keys())}", file=sys.stderr)
                    
                    if "row" in row_response:
                        row_data = row_response["row"]
                    elif "row_id" in row_response:
                        # The response IS the row
                        row_data = row_response
                
                # Case B: Response is an Object (Pydantic)
                else:
                    # Try accessing .row attribute
                    row_data = getattr(row_response, "row", None)
                    # If that failed, maybe the object itself is the row (check for row_id)
                    if not row_data and getattr(row_response, "row_id", None):
                        row_data = row_response

                if not row_data:
                    print("DEBUG: Still unable to find row data after fallback checks.", file=sys.stderr)
                    return jsonify({"success": False, "status": "pending"}), 200

                # 3. Helper to safely extract cell values
                def get_cell_val(data_row, key):
                    # Step 1: Access the column/cell
                    if isinstance(data_row, dict):
                        cell = data_row.get(key)
                    else:
                        cell = getattr(data_row, key, None)
                    
                    if not cell: return None

                    # Step 2: Access the 'value' inside the cell
                    if isinstance(cell, dict):
                        return cell.get("value")
                    else:
                        return getattr(cell, "value", None)

                # 4. Extract content
                analysis_text = get_cell_val(row_data, "route_analysis")
                pps_text = get_cell_val(row_data, "selected_pps")
                tags_text = get_cell_val(row_data, "decoded_tags")

                # 5. Check completion
                if analysis_text and pps_text:
                    
                    # --- CLEANUP: Limit selected_pps to just the name ---
                    # Logic: If output is like "The best PPS is Hall A", we try to keep just "Hall A".
                    # This is a heuristic. Ideally, update JamAI prompts to be concise.
                    clean_pps = pps_text
                    
                    # Remove common prefixes (Case insensitive)
                    prefixes = ["The best match is", "The best PPS is", "Selected PPS:", "Best Option:"]
                    for prefix in prefixes:
                        if prefix.lower() in clean_pps.lower():
                            # split and take the part after the prefix
                            clean_pps = re.split(prefix, clean_pps, flags=re.IGNORECASE)[1]
                    
                    # Clean up punctuation/markdown
                    clean_pps = clean_pps.strip(" .*:_")

                    return jsonify({
                        "success": True,
                        "status": "complete",
                        "analysis": analysis_text,
                        "tags": tags_text if tags_text else "",
                        "selected_pps": clean_pps
                    }), 200
                
                return jsonify({
                    "success": False, 
                    "status": "pending", 
                    "row_id": row_id_to_fetch
                }), 200

            except Exception as e:
                print(f"ERROR in polling loop: {e}", file=sys.stderr)
                # Return the error details so we can see them in frontend if needed
                return jsonify({
                    "success": False, 
                    "status": "pending", 
                    "error_details": str(e),
                    "row_id": row_id_to_fetch
                }), 200

        # =========================================================
        # MODE 1: SUBMIT JOB
        # =========================================================
        else:
            print("DEBUG: Submitting new job...", file=sys.stderr)
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
            
            # Robust extraction of row_id from submission
            row_id = None
            if isinstance(completion, dict):
                rows = completion.get("rows", [])
                if rows:
                    # check if row is dict or object
                    first_row = rows[0]
                    if isinstance(first_row, dict):
                        row_id = first_row.get("row_id")
                    else:
                        row_id = getattr(first_row, "row_id", None)
            else:
                if completion.rows:
                    row_id = completion.rows[0].row_id

            if not row_id:
                return jsonify({"error": "Failed to submit job - no Row ID returned"}), 500

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