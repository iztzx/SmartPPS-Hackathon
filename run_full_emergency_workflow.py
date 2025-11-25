#!/usr/bin/env python3
"""
JamAI Full Emergency Workflow:
1. Ensure 'emergency_routing' Action Table exists (creation step).
2. Upload SOP knowledge (logs to 'emergency_routing' table for RAG).
3. Decode user input (LLM Call 1).
4. Route optimal PPS using RAG grounded on:
    a) 'pps_knowledge' table (assumed pre-populated).
    b) SOPs logged in 'emergency_routing' table.
5. Log decoding and routing results to 'emergency_routing' Action Table.

Dependencies: requests (pip install requests)

Usage (Set environment variables):
  $env:JAMAI_PAT = '...'
  $env:JAMAI_PROJECT_ID = 'proj_xxx'
  $env:JAMAI_API_URL = 'https://api.jamaibase.com/v1/generate/content'
  $env:JAMAI_TABLE_API_URL = 'https://api.jamaibase.com/api/v2/gen_tables/action/rows/add'
  
  python create_action_table_and_run.py --text "4 people, one bedridden, one cat"
"""
import os
import sys
import json
import argparse
from datetime import datetime

try:
    import requests
except Exception:
    requests = None
    print('ERROR: requests library required (pip install requests)', file=sys.stderr)
    sys.exit(2)

# --- Shared Data ---
# Static PPS data retained for logging/auditing context only, not passed to LLM prompt.
STATIC_PPS_FOR_DISPLAY = [
    { 'id': 1, 'name': 'PPS North (Sekolah)', 'distance_km': 1.0, 'features': '2nd floor classrooms only, No lift', 'constraints': 'Cannot accommodate bedridden patients (stairs).'},
    { 'id': 2, 'name': 'PPS Central (Dewan)', 'distance_km': 2.0, 'features': 'Ground floor access, Ample parking', 'constraints': "Strict 'No Animals' policy."},
    { 'id': 3, 'name': 'PPS South (Kolej)', 'distance_km': 4.0, 'features': 'OKU toilets, Designated outdoor pet area, Ground floor halls', 'constraints': 'None relevant to standard needs.'}
]

SOP_KNOWLEDGE = (
    "Standard Operating Procedures for Malaysian Flood Mitigation (summary):\n"
    "1) Monitor official weather and agensi kerajaan updates; follow evacuation orders immediately.\n"
    "2) Prioritise evacuation of vulnerable persons: elderly, bedridden, infants, pregnant women, and persons with disabilities (OKU).\n"
    "3) Pets: declare animals at registration; some PPS allow pets in designated areas—bring carriers and food.\n"
    "4) Bring essential documents (ICs), medications, minimal bedding, drinking water, and basic food.\n"
)
# --- Configuration & Utility Functions ---

def get_config():
    """Reads configuration from environment variables."""
    pat = os.environ.get('JAMAI_PAT') or ''
    project_id = os.environ.get('JAMAI_PROJECT_ID') or ''
    api_url = os.environ.get('JAMAI_API_URL') or ''
    table_api_url = os.environ.get('JAMAI_TABLE_API_URL') or ''
    return pat, project_id, api_url, table_api_url

def make_headers(pat, project_id=None, content_type='application/json'):
    """Creates standard headers for JamAI requests."""
    headers = {'Content-Type': content_type}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'
    if project_id:
        headers['X-PROJECT-ID'] = project_id
        headers['X-Project-Id'] = project_id
    return headers

def call_jamai_api(url, pat, payload, project_id=None, method='POST', timeout=30):
    """Generic function to call JamAI API endpoints."""
    headers = make_headers(pat, project_id)
    try:
        resp = requests.request(method, url, headers=headers, data=json.dumps(payload), timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body
    except Exception as e:
        return None, str(e)

# --- Action Table Management ---

def create_action_table_if_not_exists(pat, project_id, api_url, table_name='emergency_routing'):
    """
    Simulates checking and creating the Action Table schema using the JamAI Management API.
    NOTE: The specific endpoint might vary, this uses a common /tables path.
    The primary goal is to ensure the table structure is known.
    """
    print(f'\n--- Checking/Creating Action Table: {table_name} ---')
    
    # 1. Define the schema based on the plan from the previous turn
    schema_payload = {
        'table_id': table_name,
        'title': 'Emergency Routing Workflow Log',
        'is_action_table': True,
        'description': 'Logs all decoding, routing, and SOP upload actions.',
        'schema': {
            'id': {'column_type': 'input', 'data_type': 'text'},
            'action': {'column_type': 'input', 'data_type': 'text'}, # decode_vulnerabilities, route_optimal_pps, sop_upload
            'created_at': {'column_type': 'input', 'data_type': 'text'},
            'input': {'column_type': 'input', 'data_type': 'text'},
            'input_tags': {'column_type': 'input', 'data_type': 'list'},
            'location': {'column_type': 'input', 'data_type': 'text'},
            'decoded_tags': {'column_type': 'LLM Output', 'data_type': 'list'},
            'selected_pps': {'column_type': 'LLM Output', 'data_type': 'text'},
            'analysis_text': {'column_type': 'LLM Output', 'data_type': 'text'},
            'pps_data': {'column_type': 'Python Output', 'data_type': 'json'}, # For auditing/logging
            'text': {'column_type': 'Python Output', 'data_type': 'text'}, # For SOP content
        }
    }
    
    # NOTE: Assuming a JamAI Management endpoint for table creation (e.g., /v1/projects/{id}/tables)
    base = api_url.split('/v1')[0].rstrip('/') if '/v1' in api_url else api_url.rstrip('/')
    management_url = f"{base}/v1/projects/{project_id}/tables"
    
    # Simplified check/create simulation: attempt creation or assume it exists if API is non-standard
    
    # Try to create it (POST request)
    status, body = call_jamai_api(management_url, pat, schema_payload, project_id, method='POST')
    
    if status in [200, 201]:
        print(f'✅ Action Table "{table_name}" created or updated successfully.')
        return True
    elif status is None:
        print(f'Warning: Network error connecting to management API. Assuming table exists. Error: {body}')
        return False
    elif status == 409: # Conflict: Table already exists
        print(f'⚠️ Action Table "{table_name}" already exists (409 Conflict). Skipping creation.')
        return True
    else:
        print(f'❌ Failed to create/check Action Table (Status {status}). You may need to create it manually.')
        print(f'Response Body: {body}')
        return False

# --- Knowledge Upload and LLM Calls ---

def upload_sop_knowledge(pat, project_id, table_api_url):
    """Uploads SOP as a RAG source into the emergency_routing table."""
    print('\n--- Uploading SOP Knowledge (emergency_routing table) ---')

    # Row for the emergency_routing table (action: sop_upload)
    sop_row = {
        'id': f'sop-{int(datetime.utcnow().timestamp())}',
        'action': 'sop_upload',
        'title': 'Malaysian Flood SOP (summary)',
        'text': SOP_KNOWLEDGE, # This 'text' field is the RAG source
        'source': 'safe-route-workflow',
        'created_at': datetime.utcnow().isoformat()
    }
    
    payload = {
        'table_id': 'emergency_routing',
        'data': [sop_row],
        'stream': False,
        'concurrent': False
    }

    status, body = call_jamai_api(table_api_url, pat, payload, project_id, method='POST')
    
    if status and 200 <= status < 300:
        print(f'✅ SOP upload successful to {table_api_url}')
        return True
    else:
        print(f'❌ Failed to upload SOP knowledge (Status {status}). Body: {json.dumps(body) if isinstance(body, dict) else body[:100]}...')
        return False

def decode_vulnerabilities(api_url, pat, text):
    """LLM Call 1: Decodes user text into tags."""
    print('\n--- Step 1: Decoding Vulnerabilities ---')
    system = { 'parts': [{ 'text': 'You are a data decoder using Qwen3-VL. Provide only a comma-separated list of standardized tags (e.g., "4 Pax, Bedridden, Pet/Cat").' }] }
    contents = [{ 'parts': [{ 'text': f'Action: decode_vulnerabilities\nUser Input: "{text}"' }] }]
    payload = { 'systemInstruction': system, 'contents': contents, 'model': 'qwen3-vl' }
    
    status, result = call_jamai_api(api_url, pat, payload)
    decoded_text = ''
    if status and 200 <= status < 300 and isinstance(result, dict):
        decoded_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    
    tags = [t.strip() for t in decoded_text.split(',') if t.strip()]
    
    if not tags:
        print(f"Decoding failed or returned empty result (Status: {status}). Raw: {result}")
        tags = ['Decoding Failed'] # Ensure a tag is returned for logging
        
    return tags, decoded_text, status, result


def route_optimal_pps(api_url, pat, tags, location_str='Unknown'):
    """
    LLM Call 2: Routes PPS using RAG grounded on 'pps_knowledge' and SOPs.
    The instruction explicitly requests RAG grounding.
    """
    print('\n--- Step 2: Routing Optimal PPS (RAG) ---')
    system_prompt = (
        'You are an emergency management AI using Qwen3-VL with RAG. '
        '**Query the pps_knowledge table** and the SOP knowledge (from emergency_routing table) to ground your recommendations. '
        'Analyze user needs and constraints from the RAG sources. Select the best-suited PPS. '
        'Provide reasoning and end with "BEST MATCH: <PPS name>".'
    )
    user_query = f"User Needs: {'; '.join(tags)}. Location: {location_str}. Query pps_knowledge table and SOP knowledge for available PPS centers and select the best match."
    
    payload = { 'systemInstruction': { 'parts': [{ 'text': system_prompt }] }, 'contents': [{ 'parts': [{ 'text': user_query }] }], 'model': 'qwen3-vl' }
    
    status, result = call_jamai_api(api_url, pat, payload)
    full_text = ''
    best = None
    
    if status and 200 <= status < 300 and isinstance(result, dict):
        full_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        # Parse BEST MATCH from the last lines
        for line in full_text.splitlines()[::-1]:
            if line.strip().upper().startswith('BEST MATCH:'):
                best = line.split(':',1)[1].strip()
                break
    
    if not best:
        print(f"Routing failed or best match not parsed (Status: {status}). Raw: {full_text[:100]}")

    return best, full_text, status, result

# --- Log Results to Action Table ---

def log_workflow_results(pat, project_id, table_api_url, decode_row, route_row):
    """Logs the results of the decode and route actions."""
    print('\n--- Logging Workflow Results (emergency_routing table) ---')

    rows_to_log = [decode_row, route_row]
    payload = {
        'table_id': 'emergency_routing',
        'data': rows_to_log,
        'stream': False,
        'concurrent': False
    }

    status, body = call_jamai_api(table_api_url, pat, payload, project_id, method='POST')

    if status and 200 <= status < 300:
        print(f'✅ Workflow results logged successfully to {table_api_url}')
        return True
    else:
        print(f'❌ Failed to log workflow results (Status {status}). Body: {json.dumps(body) if isinstance(body, dict) else body[:100]}...')
        return False

# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', '-t', required=True, help='User free-text describing situation')
    parser.add_argument('--location', '-l', default='Unknown', help='Optional location string')
    args = parser.parse_args()

    pat, project_id, api_url, table_api_url = get_config()
    
    if not all([pat, project_id, api_url, table_api_url]):
        print('ERROR: Set JAMAI_PAT, JAMAI_PROJECT_ID, JAMAI_API_URL (LLM), and JAMAI_TABLE_API_URL (Action Table) environment variables.', file=sys.stderr)
        sys.exit(2)

    # 1. Setup Table and Knowledge Base
    if not create_action_table_if_not_exists(pat, project_id, api_url):
         print("Warning: Skipping workflow execution due to table creation failure.")
         sys.exit(1)
         
    upload_sop_knowledge(pat, project_id, table_api_url)

    # 2. Decode vulnerabilities (LLM Call 1)
    tags, _, s1, _ = decode_vulnerabilities(api_url, pat, args.text)
    print(f'Decoded tags: {tags}')

    timestamp1 = datetime.utcnow().isoformat()
    decode_row = {
        'id': f'decode-{int(datetime.utcnow().timestamp())}-1',
        'action': 'decode_vulnerabilities',
        'input': args.text,
        'location': args.location,
        'decoded_tags': tags,
        'pps_data': STATIC_PPS_FOR_DISPLAY,
        'created_at': timestamp1
    }

    # 3. Route optimal PPS (LLM Call 2 - RAG)
    best, analysis_text, s2, _ = route_optimal_pps(api_url, pat, tags, args.location)
    print(f'Best match: {best}')

    timestamp2 = datetime.utcnow().isoformat()
    route_row = {
        'id': f'route-{int(datetime.utcnow().timestamp())}-2',
        'action': 'route_optimal_pps',
        'input_tags': tags,
        'location': args.location,
        'selected_pps': best,
        'analysis_text': analysis_text,
        'pps_data': STATIC_PPS_FOR_DISPLAY,
        'created_at': timestamp2
    }

    # 4. Log all results
    log_workflow_results(pat, project_id, table_api_url, decode_row, route_row)
    
    print('\n--- Workflow Finished ---')
    if best:
        print(f'SUCCESS: Recommended PPS is {best}')
    else:
        print('WARNING: Could not determine the best match.')


if __name__ == '__main__':
    main()