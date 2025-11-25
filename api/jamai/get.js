// api/jamai/get.js
export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const JAMAI_PAT = process.env.JAMAI_PAT;
    const JAMAI_PROJECT_ID = process.env.JAMAI_PROJECT_ID;
    const JAMAI_API_URL = process.env.JAMAI_API_URL || "https://api.jamai.ai";

    const response = await fetch(`${JAMAI_API_URL}/api/v2/gen_tables/pps_routing/rows`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${JAMAI_PAT}`,
        "X-Project-Id": JAMAI_PROJECT_ID
      }
    });

    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Internal Server Error" });
  }
}
