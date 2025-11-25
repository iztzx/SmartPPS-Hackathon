// /api/jamai-create.js
export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { input } = req.body;
  const { user_input, location, familyData } = input;

  const headers = {
    'Authorization': `Bearer ${process.env.JAWAT_PAT}`,
    'Content-Type': 'application/json'
  };

  try {
    // Step 1: Decoding LLM
    const decodeRes = await fetch(`${process.env.JAWAT_API_URL}/v1/decode`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text: user_input })
    });
    const decodeData = await decodeRes.json();
    const decoded_tags = decodeData.tags || [];

    // Step 2: Routing LLM
    const routeRes = await fetch(`${process.env.JAWAT_API_URL}/v1/route`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        decoded_tags,
        location_details: location,
        sop_context: 'SOP_KNOWLEDGE',
        pps_context: 'PPS_KNOWLEDGE_TEXT'
      })
    });
    const routeData = await routeRes.json();

    return res.status(200).json({
      jamai_status: 'success',
      output: {
        decoded_tags: decoded_tags.join(', '),
        analysis_text: routeData.analysis,
        selected_pps: routeData.best_match
      }
    });

  } catch (err) {
    console.error('JamAI error:', err);
    return res.status(500).json({ jamai_status: 'error', message: err.message });
  }
}
