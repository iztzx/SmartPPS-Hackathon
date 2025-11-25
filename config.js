// config.js

// Replace these placeholders with your actual JamAI Base credentials and endpoints.

// 1. CRITICAL: JamAI Personal Access Token (PAT)
window.JAMAI_PAT = "mypat"; 

// 2. CRITICAL: JamAI Project ID
window.JAMAI_PROJECT_ID = "proj_b4b113dc379b88886dc8e437"; 

// 3. CRITICAL FIX: JamAI LLM Inference API URL
// This endpoint must be the full path to your LLM model's generation endpoint.
// Example uses a common format:
window.JAMAI_API_URL = 'https://api.jamaibase.com/v1/generate/content'; 

// 4. RECOMMENDED: JamAI Table API URL
// This is used by the Python script and the HTML upload/logging button to add rows.
// Use the full Add Rows endpoint for generative/action tables.
window.JAMAI_TABLE_API_URL = 'https://api.jamaibase.com/api/v2/gen_tables/action/rows/add';