from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

# --- CONFIGURATION ---
JAMAI_API_BASE = "https://api.jamaibase.com/api"
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
            
            location_str = f"{location.get('city', 'Unknown')}, {location.get('region', 'Malaysia')}"

            # 2. Build Payload for JamAI Action Table API
            # Docs: https://jamaibase.readme.io/reference/add_rows_api_v2_gen_tables__table_type__rows_add_post
            payload = {
                "table_id": JAMAI_TABLE_ID,
                "data": [{
                    "user_input": description,
                    "location_details": location_str
                }],
                "stream": False,
                "concurrent": True
            }

            # 3. Send Request using standard urllib (No heavy SDK)
            url = f"{JAMAI_API_BASE}/v1/gen_tables/action/rows/add"
            headers = {
                'Authorization': f'Bearer {JAMAI_PAT}',
                'X-PROJECT-ID': JAMAI_PROJECT_ID,
                'Content-Type': 'application/json'
            }

            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'), 
                headers=headers, 
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            # 4. Process Response
            # The API returns the added rows with their generated columns
            if 'rows' in result and len(result['rows']) > 0:
                row_columns = result['rows'][0]['columns']
                
                # Helper to extract value safely
                def get_val(col_name):
                    col = row_columns.get(col_name)
                    # Handle different response shapes (sometimes 'text', sometimes 'value')
                    if not col: return "N/A"
                    if isinstance(col, dict): return col.get('text') or col.get('value') or "N/A"
                    return str(col)

                decoded_tags = get_val("decoded_tags")
                analysis_text = get_val("route_analysis")
                
                # Extract PPS logic
                selected_pps = "Check Analysis"
                if "BEST MATCH:" in analysis_text:
                    try:
                        selected_pps = analysis_text.split("BEST MATCH:")[1].split("\n")[0].strip("* ")
                    except:
                        pass

                response_payload = {
                    "jamai_status": "success",
                    "output": {
                        "decoded_tags": decoded_tags,
                        "analysis_text": analysis_text,
                        "selected_pps": selected_pps
                    }
                }
            else:
                response_payload = {
                    "jamai_status": "success",
                    "output": {
                        "decoded_tags": "Processing...",
                        "analysis_text": "Request queued.",
                        "selected_pps": "Wait"
                    }
                }

            self._set_headers(200)
            self.wfile.write(json.dumps(response_payload).encode('utf-8'))

        except Exception as e:
            # Error Handling
            self._set_headers(500)
            self.wfile.write(json.dumps({
                "error": True, 
                "message": f"Server Error: {str(e)}",
                "jamai_status": "error"
            }).encode('utf-8'))