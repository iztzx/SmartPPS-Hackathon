// Small runtime config file for JamAI credentials and non-sensitive defaults.
// WARNING: Do NOT commit production secrets to a public repo. This file is intended
// for local development or private deployments only.

// JamAI Base Personal Access Token (PAT)
window.JAMAI_PAT = "jamai_pat_2e78e7a9f44d66ca4726d3520eb04477d7c02260745203df";

// 3. CRITICAL: JamAI LLM Inference API URL
// NOTE: This must point to the endpoint that accepts the {contents, systemInstruction} payload.
window.JAMAI_API_URL = 'https://api.jamaibase.com/v1/generate/content'; 

// 4. RECOMMENDED: JamAI Table API URL (Used for logging and SOP upload)
// NOTE: Set this to the preferred Add Rows endpoint for generative tables.
window.JAMAI_TABLE_API_URL = 'https://api.jamaibase.com/api/v2/gen_tables/action/rows/add';

// By default, disable Supabase-backed auth and remote writes so the app works
// immediately without any login. Set to `true` to enable Supabase behavior.
window.ENABLE_SUPABASE = false;

// If you prefer the app to start in authenticated mode with Supabase enabled,
// set `window.ENABLE_SUPABASE = true` and provide SUPABASE_URL/KEY via safe injection.

// You may also add other client-side defaults here if needed.

// To keep secrets safe in production, provide these values via a secure server-side
// endpoint or environment injection rather than embedding them in a static file.
