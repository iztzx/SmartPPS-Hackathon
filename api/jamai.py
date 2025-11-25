from http.server import BaseHTTPRequestHandler
import json
import os
import requests

# --- Configuration (Set these in your Vercel/JamAI environment variables) ---
JAMAI_API_URL = os.environ.get("JAMAI_API_URL", "https://api.jamaibase.com/v1/projects")
JAMAI_PROJECT_ID = os.environ.get("JAMAI_PROJECT_ID")
JAMAI_PAT = os.environ.get("JAMAI_PAT")
# The name of the action table in JamAI for storing the routing history
JAMAI_TABLE_ID = "emergency_routing"

# Standard SOP Knowledge for RAG (grounding the LLM)
SOP_KNOWLEDGE = """Standard Operating Procedures for Malaysian Flood Mitigation (summary):
1) Monitor official weather and agensi kerajaan updates; follow evacuation orders immediately.
2) Prioritise evacuation of vulnerable persons: elderly, bedridden, infants, pregnant women, and persons with disabilities (OKU).
3) Pets: declare animals at registration; some PPS allow pets in designated areas—bring carriers and food.
4) Bring essential documents (ICs), medications, minimal bedding, drinking water, and basic food; label items with head of family name.
5) Hygiene: bring face masks, soap, hand sanitizer, and maintain distancing where possible.
6) Sanitation: use provided toilets; report sanitary issues to PPS officer.
7) Electrical safety: avoid floodwaters, do not use electrical appliances in water; generators must be outdoors with safe ventilation.
8) Medical emergencies: inform PPS medical teams immediately; register special needs on arrival for priority assistance.
9) Registration: register at the PPS counter, obtain family token/QR, comply with volunteer instructions.
10) Communication: keep phones charged, use designated family contact points, and do not re-enter flooded areas until declared safe."""

# Mock PPS Knowledge (This should ideally be fetched from a JamAI table using RAG)
# For this example, we'll embed a simple list that the LLM will see.
# In a real setup, this would be an actual 'pps_knowledge' table in JamAI.
PPS_KNOWLEDGE_TEXT = """
PPS_KNOWLEDGE (Active Centers):
- PPS North (Sekolah) | lat:3.15 lon:101.68 | features: OKU ramp, pet-friendly area, large capacity (500), temporary medical post | capacity: 500
- PPS South (Dewan Komuniti) | lat:3.12 lon:101.72 | features: Small capacity (100), no pet-friendly area, accessible ground floor | capacity: 100
- PPS West (Masjid Besar) | lat:3.13 lon:101.65 | features: Large capacity (400), no specific OKU facilities, food distribution point | capacity: 400
- PPS East (Church Hall) | lat:3.16 lon:101.70 | features: Medium capacity (200), OKU access, elderly focus | capacity: 200
"""

class handler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        """Handles POST request to create a new routing entry and trigger LLM processing."""
        if self.path == '/api/jamai/create':
            return self._create_routing_entry()
        self.send_error(404)

    def do_GET(self):
        """Handles GET request to fetch the latest routing entry."""
        if self.path == '/api/jamai/get':
            return self._get_latest_routing_entry()
        self.send_error(404)

    def _get_headers(self):
        """Utility to generate required JamAI headers."""
        return {
            'Authorization': f'Bearer {JAMAI_PAT}',
            'X-Project-Id': JAMAI_PROJECT_ID,
            'Content-Type': 'application/json',
        }

    def _create_routing_entry(self):
        """
        Processes user input, calls the LLM via JamAI (using Add Rows with columns),
        and stores the result in the 'emergency_routing' table.
        """
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        payload = json.loads(post_data)
        
        # 1. Prepare Inputs
        location = payload.get('input', {}).get('location', {})
        description = payload.get('input', {}).get('description', '')
        
        location_string = f"{location.get('city', 'N/A')}, {location.get('region', 'N/A')} (Lat: {location.get('lat', 0):.4f}, Lon: {location.get('lon', 0):.4f})"

        # System Instruction for LLM
        system_prompt_decode = "You are a data decoder. Analyze the following emergency situation. Extract and list the distinct vulnerabilities, special needs, and key family details relevant to a relief center (PPS). Output ONLY a comma-separated list of structured keywords. Mandatory keywords: Family size (e.g., '5 Pax'). If no other vulnerability is mentioned, only output the 'X Pax' tag. Other keywords: 'Warga Emas/Bedridden', 'Pet/Cat', 'Wheelchair User (OKU)', 'Dietary Restrictions'. Do not include any other text."
        
        system_prompt_route = "You are an emergency management AI. Use the supplied SOP knowledge and the PPS knowledge table (RAG) to ground recommendations. Analyze user vulnerabilities and available PPS to select the single, best-suited center. Provide a concise Chain-of-Thought explaining acceptance/rejection based on user needs and SOPs. Finally, output the name of the BEST MATCH in its own, single line at the end (e.g., BEST MATCH: PPS North (Sekolah)). Do not include any other text after 'BEST MATCH'."
        
        # User Query combining all context for the routing step
        routing_query = f"""User Needs: <PLACEHOLDER_FOR_DECODED_TAGS>. 
Location: {location_string}. 
SOP: {SOP_KNOWLEDGE}
{PPS_KNOWLEDGE_TEXT}
"""

        # 2. Prepare the `add_rows` API payload with completions
        api_payload = {
            "table_id": JAMAI_TABLE_ID,
            "data": [{
                "action": "routing_request",
                "user_input": description,
                "location_details": location_string,
                "created_at": requests.utils.default_headers().get('Date', ''),
            }],
            "completion_columns": {
                # Column 1: Semantic Decoding
                "decoded_tags": {
                    "model": "gemini-2.5-flash",
                    "prompt": description,
                    "system_instruction": system_prompt_decode,
                },
                # Column 2: Intelligent Routing (Chain of two LLM steps)
                "route_analysis": {
                    "model": "gemini-2.5-flash",
                    "prompt": routing_query,
                    "system_instruction": system_prompt_route,
                    "prompt_dependencies": {
                        # Use the result of 'decoded_tags' to populate the placeholder
                        "decoded_tags": "User Needs: {result}. Location: {location_details}. SOP: {SOP_KNOWLEDGE}\n\n{PPS_KNOWLEDGE_TEXT}"
                    }
                }
            },
            "stream": False,
            "concurrent": False
        }
        
        # 3. Call JamAI
        try:
            # We use the generic tables endpoint, not the project endpoint for Add Rows API v2
            table_api_url = f"{JAMAI_API_URL.split('/v1')[0]}/api/v2/gen_tables/action/rows/add"
            response = requests.post(table_api_url, headers=self._get_headers(), json=api_payload, timeout=60)
            
            if response.status_code == 200:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                # Parse the response to extract the LLM output
                response_json = response.json()
                rows = response_json.get('rows', [])
                output = {}
                
                if rows:
                    cols = rows[0].get('columns', {})
                    
                    # Extract Decoded Tags
                    decoded_tags_comp = cols.get('decoded_tags', {})
                    decoded_tags_text = decoded_tags_comp.get('choices', [{}])[0].get('message', {}).get('content', '') or \
                                        decoded_tags_comp.get('choices', [{}])[0].get('text', '') 
                    
                    # Extract Route Analysis and Best Match
                    route_analysis_comp = cols.get('route_analysis', {})
                    analysis_text = route_analysis_comp.get('choices', [{}])[0].get('message', {}).get('content', '') or \
                                    route_analysis_comp.get('choices', [{}])[0].get('text', '')
                    
                    best_match = ""
                    # The prompt ensures BEST MATCH: is the last line
                    if analysis_text:
                        last_line = [line.strip() for line in analysis_text.split('\n') if line.strip().upper().startswith("BEST MATCH:")][-1]
                        best_match = last_line.replace("BEST MATCH:", "").strip()
                        analysis_text = analysis_text.replace(last_line, "").strip() # Remove best match from analysis text

                    output = {
                        "decoded_tags": decoded_tags_text,
                        "analysis_text": analysis_text,
                        "selected_pps": best_match
                    }
                
                # Return the processed LLM output to the frontend
                self.wfile.write(json.dumps({
                    "message": "Routing entry created and processed successfully.",
                    "jamai_status": "success",
                    "output": output
                }).encode('utf-8'))
                
            else:
                self.send_error(response.status_code, f"JamAI API Error: {response.text}")
                
        except Exception as e:
            self.send_error(500, f"Server Error: {str(e)}")


    def _get_latest_routing_entry(self):
        """
        Fetches the single latest entry from the 'emergency_routing' table.
        This is a simplified way to retrieve the result after the POST.
        """
        # We need the List Rows API URL
        table_list_api_url = f"{JAMAI_API_URL.split('/v1')[0]}/api/v2/gen_tables/action/rows/list"

        try:
            params = {
                "table_id": JAMAI_TABLE_ID,
                "limit": 1,
                "order_by": "created_at",
                "order": "desc"
            }
            response = requests.get(table_list_api_url, headers=self._get_headers(), params=params, timeout=30)
            
            if response.status_code == 200:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(response.content)
            else:
                self.send_error(response.status_code, f"JamAI List API Error: {response.text}")

        except Exception as e:
            self.send_error(500, f"Server Error: {str(e)}")