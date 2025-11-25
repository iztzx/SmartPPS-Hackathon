from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import time
from typing import Optional
from jamaibase import JamAI, protocol as p

app = FastAPI()

# Allow CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Configuration --
# Ensure these are set in your Vercel Environment Variables
PROJECT_ID = os.environ.get("JAMAI_PROJECT_ID")
API_URL = os.environ.get("JAMAI_API_URL")
API_KEY = os.environ.get("JAMAI_PAT")
TABLE_ID = "emergency_routing"  # Matching your CSV filename/table name

# Initialize JamAI Client
jamai = JamAI(project_id=PROJECT_ID, api_key=API_KEY, api_url=API_URL)

class RouteRequest(BaseModel):
    user_input: str
    location_details: str

@app.post("/api/find_safe_shelter")
def find_safe_shelter(request: RouteRequest):
    try:
        # 1. Add the user input to the JamAI Action Table
        # We send the input and let the LLM columns (decoded_tags, route_analysis) generate.
        row_add_response = jamai.table.add_table_rows(
            "action",
            p.RowAddRequest(
                table_id=TABLE_ID,
                data=[{
                    "user_input": request.user_input,
                    "location_details": request.location_details,
                    "action": "analyze_vulnerability" # Explicit action trigger if needed
                }],
                stream=False
            )
        )

        if not row_add_response.rows:
            raise HTTPException(status_code=500, detail="Failed to add row to JamAI table.")

        row_id = row_add_response.rows[0].row_id

        # 2. Poll for the result (Wait for LLM "route_analysis" to complete)
        # Since RAG/LLM generation takes a few seconds, we poll the specific row.
        max_retries = 10
        for _ in range(max_retries):
            row_response = jamai.table.get_table_rows(
                "action",
                p.RowListRequest(
                    table_id=TABLE_ID,
                    row_ids=[row_id]
                )
            )
            
            if row_response.items:
                row_data = row_response.items[0]
                # Check if the output column is populated and not empty
                analysis = row_data.get("route_analysis")
                if analysis and isinstance(analysis, dict):
                    # If it's a structured object, extract text (value)
                    analysis_text = analysis.get("value", "")
                    if analysis_text:
                        return {
                            "status": "success",
                            "tags": row_data.get("decoded_tags", {}).get("value", ""),
                            "analysis": analysis_text
                        }
                elif analysis and isinstance(analysis, str) and analysis.strip():
                     return {
                            "status": "success",
                            "tags": row_data.get("decoded_tags", ""),
                            "analysis": analysis
                        }

            time.sleep(2) # Wait 2 seconds before retrying

        return {"status": "processing", "message": "Analysis is taking longer than expected. Please check back later."}

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Vercel requires the app to be exposed
# If running locally: uvicorn api.index:app --reload