# Scripts: JamAI SOP upload and Analyze+Route

This folder contains two helper scripts to interact with JamAI from your local machine:

1. `upload_sop_to_jamai.py` — uploads a single SOP row to a JamAI Action/Table endpoint.
2. `analyze_and_route.py` — performs two-step analysis (decode vulnerabilities, then route to best PPS using RAG with SOP + PPS list).

Prerequisites
- Python 3.8+
- Install `requests`:

```powershell
python -m pip install requests
```

Environment variables
- `JAMAI_PAT` (required): JamAI personal access token.
- `JAMAI_PROJECT_ID` (optional): used to build a table endpoint if `JAMAI_TABLE_API_URL` is not provided.
- `JAMAI_API_URL` (required by analyze_and_route.py): the full JamAI LLM endpoint URL (the frontend `LLM_API_URL`).
- `JAMAI_TABLE_API_URL` (optional): the explicit JamAI table endpoint to upload rows.

Examples

Upload the SOP row (HTTP fallback using `requests`):

```powershell
$env:JAMAI_PAT = 'your_pat_here'
$env:JAMAI_TABLE_API_URL = 'https://api.jamai.example/v1/projects/PROJECT_ID/tables'
python .\scripts\upload_sop_to_jamai.py
```

Run analyze + route (decode tags and get best match):

```powershell
$env:JAMAI_PAT = 'your_pat_here'
$env:JAMAI_API_URL = 'https://api.jamai.example/v1/generate'  # example LLM endpoint
python .\scripts\analyze_and_route.py --text "4 people, one bedridden, one cat" --location "Segamat, Johor"
```

Notes
- The scripts use a generic REST payload shape compatible with the frontend (JSON with `contents` and `systemInstruction`). If your JamAI installation requires a different API path or payload structure, update the `JAMAI_API_URL` and/or adapt the payloads in the scripts.
- The upload script uses a conservative `rows` payload. If the JamAI table API uses a schema with explicit `columns` or different keys, you will need to adjust the `payload` structure accordingly.
