// api/jamai.js
export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { tableName, input, output } = req.body;

    const JAMAI_PAT = process.env.JAMAI_PAT; // set in Vercel env vars
    const JAMAI_PROJECT_ID = process.env.JAMAI_PROJECT_ID;
    const JAMAI_API_URL = process.env.JAMAI_API_URL || "https://api.jamai.ai";

    const response = await fetch(`${JAMAI_API_URL}/api/v2/gen_tables/action`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${JAMAI_PAT}`,
        "X-Project-Id": JAMAI_PROJECT_ID
      },
      body: JSON.stringify({
        table_name: tableName,
        input,
        output
      })
    });

    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    console.error("JamAI API error:", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
}
