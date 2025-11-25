from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

# Environment Variables (Set these in Vercel Dashboard)
JAMAI_API_URL = os.environ.get("JAMAI_API_URL", "https://api.jamaibase.com/api/v1/gen_tables/action")
JAMAI_PROJECT_ID = os.environ.get("JAMAI_PROJECT_ID", "")
JAMAI_PAT = os.environ.get("JAMAI_PAT", "")
JAMAI_TABLE_ID = os.environ.get("JAMAI_TABLE_ID", "emergency_routing")

# Fallback LLM (Gemini) if JamAI is not configured
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"

# Knowledge Base
SOP_KNOWLEDGE = """Standard Operating Procedures for Malaysian Flood Mitigation:
1) Monitor official weather updates; follow evacuation orders immediately.
2) Prioritise vulnerable persons: elderly, bedridden, infants, pregnant women, OKU.
3) Pets: declare at registration; some PPS allow pets in designated areas.
4) Bring ICs, medications, bedding, water, basic food.
5) Maintain hygiene: masks, soap, sanitizer.
6) Register at PPS counter, obtain family token/QR.
7) Do not re-enter flooded areas until declared safe."""

PPS_KNOWLEDGE = """Available Relief Centers (PPS):
- PPS North (Sekolah): OKU ramp, pet-friendly, capacity 500, medical post
- PPS South (Dewan): Small capacity 100, ground floor accessible
- PPS West (Masjid): Large capacity 400, food distribution
- PPS East (Church): Medium capacity 200, OKU access, elderly focus"""


class handler(BaseHTTPRequestHandler):
    
    def _set_cors_headers(self):
        """Enable CORS for frontend requests"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()
    
    def do_POST(self):
        """Handle routing analysis requests"""
        if self.path == '/api/jamai/create':
            return self._create_routing()
        
        self.send_error(404, "Endpoint not found")
    
    def do_GET(self):
        """Handle data retrieval requests"""
        if self.path == '/api/jamai/get':
            return self._get_routing_history()
        
        self.send_error(404, "Endpoint not found")
    
    def _create_routing(self):
        """Process semantic input and generate routing recommendations"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Extract inputs
            user_input = data.get('input', {})
            description = user_input.get('description', '')
            location = user_input.get('location', {})
            family_data = user_input.get('familyData', {})
            
            location_str = f"{location.get('city', 'Unknown')}, {location.get('region', 'Malaysia')} (Lat: {location.get('lat', 0):.4f}, Lon: {location.get('lon', 0):.4f})"
            
            # Step 1: Decode semantic input into structured tags
            decode_prompt = f"""Analyze this emergency situation and extract vulnerabilities as comma-separated tags.
Mandatory: Family size (e.g., "5 Pax")
Optional: "Warga Emas/Bedridden", "Pet/Cat", "Wheelchair User (OKU)", "Dietary Restrictions"

User Input: "{description}"

Output ONLY the tags, nothing else."""

            decoded_tags = self._call_llm(decode_prompt, "You extract structured tags only.")
            
            # Step 2: Intelligent routing with RAG context
            routing_prompt = f"""You are an emergency management AI. Analyze and recommend the BEST relief center.

USER NEEDS: {decoded_tags}
LOCATION: {location_str}

{SOP_KNOWLEDGE}

{PPS_KNOWLEDGE}

Provide:
1. Brief analysis of each PPS suitability
2. Clear recommendation

End with: BEST MATCH: [PPS Name]"""

            analysis = self._call_llm(routing_prompt, "You are an emergency routing specialist.")
            
            # Extract best match
            best_match = "Unknown PPS"
            for line in analysis.split('\n'):
                if line.upper().startswith('BEST MATCH:'):
                    best_match = line.split(':', 1)[1].strip()
                    analysis = analysis.replace(line, '').strip()
                    break
            
            # Build response
            response_data = {
                "jamai_status": "success",
                "message": "Routing analysis completed",
                "output": {
                    "decoded_tags": decoded_tags,
                    "analysis_text": analysis,
                    "selected_pps": best_match
                },
                "metadata": {
                    "location": location_str,
                    "timestamp": self._get_timestamp()
                }
            }
            
            # Store in JamAI if configured
            if JAMAI_PAT and JAMAI_PROJECT_ID:
                self._store_in_jamai({
                    "user_input": description,
                    "location": location_str,
                    "decoded_tags": decoded_tags,
                    "analysis": analysis,
                    "selected_pps": best_match
                })
            
            # Send response
            self.send_response(200)
            self._set_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            self._send_error_response(500, f"Server error: {str(e)}")
    
    def _get_routing_history(self):
        """Retrieve routing history from JamAI"""
        try:
            if not JAMAI_PAT or not JAMAI_PROJECT_ID:
                self._send_error_response(400, "JamAI not configured")
                return
            
            # Fetch from JamAI
            url = f"{JAMAI_API_URL}/rows/list"
            headers = {
                'Authorization': f'Bearer {JAMAI_PAT}',
                'X-Project-Id': JAMAI_PROJECT_ID,
                'Content-Type': 'application/json'
            }
            
            params = {
                'table_id': JAMAI_TABLE_ID,
                'limit': 10,
                'offset': 0
            }
            
            # Build URL with params
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"
            
            req = urllib.request.Request(full_url, headers=headers, method='GET')
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            self.send_response(200)
            self._set_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self._send_error_response(500, f"Failed to retrieve history: {str(e)}")
    
    def _call_llm(self, prompt, system_instruction):
        """Call LLM API (JamAI or Gemini fallback)"""
        try:
            # Try JamAI first if configured
            if JAMAI_PAT and JAMAI_PROJECT_ID:
                return self._call_jamai_llm(prompt, system_instruction)
            
            # Fallback to Gemini
            if GEMINI_API_KEY:
                return self._call_gemini_llm(prompt, system_instruction)
            
            raise Exception("No LLM API configured (set JAMAI_PAT or GEMINI_API_KEY)")
            
        except Exception as e:
            print(f"LLM call failed: {str(e)}")
            raise
    
    def _call_jamai_llm(self, prompt, system_instruction):
        """Call JamAI Base LLM"""
        url = f"{JAMAI_API_URL}/chat/completions"
        
        payload = {
            "model": "gemini/gemini-2.0-flash-exp",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        headers = {
            'Authorization': f'Bearer {JAMAI_PAT}',
            'X-Project-Id': JAMAI_PROJECT_ID,
            'Content-Type': 'application/json'
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        return result['choices'][0]['message']['content']
    
    def _call_gemini_llm(self, prompt, system_instruction):
        """Fallback to Gemini API"""
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1000
            }
        }
        
        req = urllib.request.Request(
            GEMINI_API_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        return result['candidates'][0]['content']['parts'][0]['text']
    
    def _store_in_jamai(self, data):
        """Store routing data in JamAI action table"""
        try:
            url = f"{JAMAI_API_URL}/rows/add"
            
            payload = {
                "table_id": JAMAI_TABLE_ID,
                "data": [{
                    "action": "routing_request",
                    "user_input": data['user_input'],
                    "location_details": data['location'],
                    "decoded_tags": data['decoded_tags'],
                    "analysis": data['analysis'],
                    "selected_pps": data['selected_pps'],
                    "created_at": self._get_timestamp()
                }],
                "stream": False
            }
            
            headers = {
                'Authorization': f'Bearer {JAMAI_PAT}',
                'X-Project-Id': JAMAI_PROJECT_ID,
                'Content-Type': 'application/json'
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                print(f"Stored in JamAI: {response.status}")
                
        except Exception as e:
            print(f"Warning: Failed to store in JamAI: {str(e)}")
            # Don't fail the request if storage fails
    
    def _send_error_response(self, code, message):
        """Send JSON error response"""
        self.send_response(code)
        self._set_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        error_data = {
            "error": True,
            "message": message,
            "jamai_status": "error"
        }
        
        self.wfile.write(json.dumps(error_data).encode('utf-8'))
    
    def _get_timestamp(self):
        """Get current ISO timestamp"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'