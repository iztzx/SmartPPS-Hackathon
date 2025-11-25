from http.server import BaseHTTPRequestHandler
import json
import os
from jamaibase import JamAI, types as t

# --- CONFIGURATION ---
# Ensure these are set in your Vercel Project Settings
JAMAI_PROJECT_ID = os.environ.get("JAMAI_PROJECT_ID", "")
JAMAI_PAT = os.environ.get("JAMAI_PAT", "")
JAMAI_TABLE_ID = os.environ.get("JAMAI_TABLE_ID", "emergency_routing")

class handler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_POST(self):
        try:
            # 1. Parse Frontend Input
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            user_input_data = data.get('input', {})
            description = user_input_data.get('description', '')
            location = user_input_data.get('location', {})
            
            # Format location for the AI
            location_str = f"{location.get('city', 'Unknown')}, {location.get('region', 'Malaysia')}"

            # 2. Initialize JamAI SDK
            jamai = JamAI(project_id=JAMAI_PROJECT_ID, token=JAMAI_PAT)

            # 3. Add Row to Action Table
            # This triggers the LLM columns (decoded_tags, route_analysis) to generate automatically.
            completion = jamai.table.add_table_rows(
                table_type=t.TableType.ACTION,
                request=t.RowAddRequest(
                    table_id=JAMAI_TABLE_ID,
                    data=[{
                        "user_input": description,
                        "location_details": location_str
                    }],
                    stream=False, # We want the full result at once
                    concurrent=True
                )
            )

            # 4. Extract Results from SDK Response
            if completion.rows:
                row_data = completion.rows[0].columns
                
                # Helper to safely get text content from a column
                def get_col_text(col_id):
                    col = row_data.get(col_id)
                    return col.text if col else "N/A"

                decoded_tags = get_col_text("decoded_tags")
                analysis_text = get_col_text("route_analysis")
                
                # Extract PPS name from analysis (assuming standard format)
                selected_pps = "Check Analysis"
                if "BEST MATCH:" in analysis_text:
                    selected_pps = analysis_text.split("BEST MATCH:")[1].split("\n")[0].strip("* ")

                response_payload = {
                    "jamai_status": "success",
                    "output": {
                        "decoded_tags": decoded_tags,
                        "analysis_text": analysis_text,
                        "selected_pps": selected_pps
                    }
                }
            else:
                raise Exception("No rows returned from JamAI")

            self._set_headers(200)
            self.wfile.write(json.dumps(response_payload).encode('utf-8'))

        except Exception as e:
            # Catch all errors to prevent HTML leakage
            print(f"Error: {str(e)}")
            self._set_headers(500)
            self.wfile.write(json.dumps({
                "error": True, 
                "message": f"Server Error: {str(e)}",
                "jamai_status": "error"
            }).encode('utf-8'))