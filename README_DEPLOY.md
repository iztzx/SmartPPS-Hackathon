# Deploying SafeRoute (JamAI integration) and creating JamAI tables

Quick guide to get the project running locally, create JamAI tables, and deploy the static site to Vercel.

1) Set environment variables (locally / in Vercel):

   - `JAMAI_PAT` : your JamAI Personal Access Token (keep secret)
   - `JAMAI_PROJECT_ID` : your project id (optional for Add-Rows)
   - `JAMAI_API_URL` : e.g. `https://api.jamaibase.com`

2) Install Python dependencies (for scripts):

```powershell
python -m pip install -r requirements.txt
```

3) Create tables and run Add-Rows test (locally):

```powershell
#$env:JAMAI_PAT = 'YOUR_REAL_PAT'
#$env:JAMAI_PROJECT_ID = 'your_project_id'
#$env:JAMAI_API_URL = 'https://api.jamaibase.com'
python .\scripts\create_action_table_and_run.py
```

4) Deploy static `index.html` to Vercel:

- Commit this repo to GitHub.
- On Vercel, import the Git repository and set the Environment Variables (`JAMAI_PAT`, `JAMAI_PROJECT_ID`, `JAMAI_API_URL`, `JAMAI_TABLE_API_URL`) in the Project Settings.
- Set the framework/preset to "Static Site" (the root contains `index.html`). Vercel will serve the static site.

Notes:
- The Python scripts are intended for admin/table-creation tasks and are not executed by Vercel. To automate table creation after deploy, use the included GitHub Actions workflow.
- Keep your PAT secret; rotate if exposed.