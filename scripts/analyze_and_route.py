#!/usr/bin/env python3
"""
Analyze a free-text family situation, decode vulnerabilities, and select the best PPS using JamAI (RAG with SOP + PPS list).

This script performs two steps (mirrors the frontend):
  1) decode_vulnerabilities: send the user's free-text to JamAI and request a comma-separated set of tags.
  2) route_optimal_pps: send the decoded tags along with PPS_DATA and SOP_KNOWLEDGE to JamAI and parse the BEST MATCH.

Usage:
  export JAMAI_PAT=... JAMAI_API_URL=https://<jamai-llm-endpoint>
  python scripts/analyze_and_route.py --text "4 people, one bedridden, one cat"

Notes:
- JAMAI_API_URL should be a full LLM endpoint that accepts the payload shape {contents, systemInstruction} used by the frontend.
- If you have a JamAI Python SDK, you can adapt the `call_jamai` function to use the SDK. This script uses simple HTTP calls (requests).
"""

import os
import json
import sys
import argparse
import time

try:
    import requests
except Exception:
    requests = None

# Small PPS dataset (same content as frontend)
PPS_DATA = [
    { 'id': 1, 'name': 'PPS North (Sekolah)', 'distance_km': 1.0, 'lat': 1.5000, 'lon': 103.7500, 'features': '2nd floor classrooms only, No lift, Limited parking', 'constraints': 'Cannot accommodate bedridden patients (stairs).'},
    { 'id': 2, 'name': 'PPS Central (Dewan)', 'distance_km': 2.0, 'lat': 1.4800, 'lon': 103.7300, 'features': 'Ground floor access, Ample parking, Strict pet policy', 'constraints': "Strict 'No Animals' policy."},
    { 'id': 3, 'name': 'PPS South (Kolej)', 'distance_km': 4.0, 'lat': 1.4500, 'lon': 103.7200, 'features': 'OKU toilets, Designated outdoor pet area, Ground floor halls', 'constraints': 'None relevant to standard needs.'}
]

SOP_KNOWLEDGE = (
    "Standard Operating Procedures for Malaysian Flood Mitigation (summary):\n"
    "1) Monitor official weather and agensi kerajaan updates; follow evacuation orders immediately.\n"
    "2) Prioritise evacuation of vulnerable persons: elderly, bedridden, infants, pregnant women, and persons with disabilities (OKU).\n"
    "3) Pets: declare animals at registration; some PPS allow pets in designated areas—bring carriers and food.\n"
    "4) Bring essential documents (ICs), medications, minimal bedding, drinking water, and basic food; label items with head of family name.\n"
    "5) Hygiene: bring face masks, soap, hand sanitizer, and maintain distancing where possible.\n"
    "6) Sanitation: use provided toilets; report sanitary issues to PPS officer.\n"
    "7) Electrical safety: avoid floodwaters, do not use electrical appliances in water; generators must be outdoors with safe ventilation.\n"
    "8) Medical emergencies: inform PPS medical teams immediately; register special needs on arrival for priority assistance.\n"
    "9) Registration: register at the PPS counter, obtain family token/QR, comply with volunteer instructions.\n"
    "10) Communication: keep phones charged, use designated family contact points, and do not re-enter flooded areas until declared safe."
)


def get_config():
    pat = os.environ.get('JAMAI_PAT') or ''
    api_url = os.environ.get('JAMAI_API_URL') or ''
    return pat, api_url


def call_jamai(api_url, pat, payload, timeout=30):
    if not api_url:
        raise RuntimeError('JAMAI_API_URL must be set (full LLM endpoint URL).')
    if requests is None:
        raise RuntimeError('requests library required: pip install requests')

    headers = {'Content-Type': 'application/json'}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'

    resp = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def decode_vulnerabilities(api_url, pat, text):
    system = { 'parts': [{ 'text': 'You are a data decoder. Provide only a comma-separated list of standardized tags.' }] }
    contents = [{ 'parts': [{ 'text': f'Analyze the following emergency situation and output a comma-separated list of tags. User Input: "{text}"' }] }]
    payload = { 'systemInstruction': system, 'contents': contents }

    status, result = call_jamai(api_url, pat, payload)
    if isinstance(result, dict):
        decoded_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    else:
        decoded_text = str(result)

    tags = [t.strip() for t in decoded_text.split(',') if t.strip()]
    return tags, decoded_text, status, result


def route_optimal_pps(api_url, pat, decoded_tags, location_str='Unknown Location'):
    system_prompt = (
        "You are an emergency management AI. Use the supplied SOP knowledge and the PPS list to ground your recommendations (RAG). Analyze user vulnerabilities and available PPS to select the single, best-suited center. Provide a concise Chain-of-Thought explaining acceptance/rejection based on user needs and SOPs. Finally, output the name of the BEST MATCH in its own, single line at the end (e.g., BEST MATCH: PPS North (Sekolah))."
    )

    user_query = f"User Needs: {'; '.join(decoded_tags)}. Location: {location_str}. PPS: {json.dumps(PPS_DATA)}. SOP: {SOP_KNOWLEDGE}"

    payload = {
        'systemInstruction': { 'parts': [{ 'text': system_prompt }] },
        'contents': [{ 'parts': [{ 'text': user_query }] }]
    }

    status, result = call_jamai(api_url, pat, payload)
    full_text = ''
    if isinstance(result, dict):
        full_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    else:
        full_text = str(result)

    # Try to parse BEST MATCH line
    best = None
    for line in full_text.splitlines()[::-1]:
        if line.strip().upper().startswith('BEST MATCH:'):
            best = line.split(':', 1)[1].strip()
            break

    return best, full_text, status, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', '-t', help='Free text describing family situation', required=True)
    parser.add_argument('--location', '-l', help='Optional location string for grounding', default='Unknown')
    args = parser.parse_args()

    pat, api_url = get_config()
    if not api_url:
        print('ERROR: Set JAMAI_API_URL environment variable to your JamAI LLM endpoint URL.', file=sys.stderr)
        sys.exit(2)

    print('Decoding vulnerabilities...')
    tags, decoded_text, s1, r1 = decode_vulnerabilities(api_url, pat, args.text)
    print('Decoded tags:', tags)
    print('Raw decoder output:', decoded_text[:1000])

    print('\nRouting with RAG (SOP + PPS list)...')
    best, analysis, s2, r2 = route_optimal_pps(api_url, pat, tags, args.location)

    print('\n--- Full Analysis (truncated) ---')
    print(analysis[:4000])
    print('\nBest Match:', best)

    # exit code: 0 if best found, else 1
    sys.exit(0 if best else 1)


if __name__ == '__main__':
    main()
