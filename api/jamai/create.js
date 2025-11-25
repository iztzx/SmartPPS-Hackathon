// api/jamai/create.js
export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { input } = req.body;

  try {
    const JAMAI_PAT = process.env.JAMAI_PAT;
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
        table_name: "pps_routing",
        input,
        // JamAI LLM will generate output automatically
      })
    });

    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Internal Server Error" });
  }
}
