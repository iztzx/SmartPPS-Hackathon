// /api/jamai-create.js
export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { input } = req.body;
  const { description, location, familyData } = input;

  const headers = {
    'Authorization': `Bearer ${process.env.JAWAT_PAT}`,
    'Content-Type': 'application/json'
  };

  try {
    // Step 1: Decode user input
    const decodeRes = await fetch(`${process.env.JAWAT_API_URL}/decode`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text: description })
    });
    const decodeJson = await decodeRes.json();
    const decoded_tags = decodeJson.tags || [];

    // Step 2: Routing analysis
    const routeRes = await fetch(`${process.env.JAWAT_API_URL}/route`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        decoded_tags,
        location_details: location,
        sop_context: 'SOP_KNOWLEDGE',
        pps_context: 'PPS_KNOWLEDGE_TEXT'
      })
    });
    const routeJson = await routeRes.json();

    return res.status(200).json({
      jamai_status: 'success',
      output: {
        decoded_tags: decoded_tags.join(', '),
        analysis_text: routeJson.analysis,
        selected_pps: routeJson.best_match
      }
    });

  } catch (err) {
    console.error('JamAI error:', err);
    return res.status(500).json({ jamai_status: 'error', message: err.message });
  }
}
