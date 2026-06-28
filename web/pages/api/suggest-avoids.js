import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

const MIN_REASONS_NEEDED = 3;
const MAX_REASONS_CONSIDERED = 20;

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token } = req.body || {};
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  if (!user.anthropic_api_key) {
    return res.status(400).json({ error: "Add your Anthropic API key in Settings first" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data: skipped, error } = await supabase
      .from("seen_jobs")
      .select("title, company_name, skip_reason")
      .eq("user_id", user.id)
      .eq("status", "skip")
      .not("skip_reason", "is", null)
      .order("created_at", { ascending: false })
      .limit(MAX_REASONS_CONSIDERED);
    if (error) throw error;

    if (!skipped || skipped.length < MIN_REASONS_NEEDED) {
      return res.status(200).json({
        hasPattern: false,
        message: `Need at least ${MIN_REASONS_NEEDED} skip reasons to look for a pattern - you have ${skipped?.length || 0} so far.`,
      });
    }

    const examplesText = skipped
      .map((j) => `- "${j.title}" at ${j.company_name}: ${j.skip_reason}`)
      .join("\n");

    const prompt = `Here are jobs a candidate skipped, with their reasons:\n${examplesText}\n\nIs there a recurring theme across these reasons (e.g. a role function, seniority level, work arrangement, or company type they consistently avoid)? Only flag a pattern if at least 3 of these reasons share a common, generalizable thread.\n\nReturn ONLY valid JSON, no markdown:\n{\n  "has_pattern": <true or false>,\n  "suggested_avoid": "<short phrase, 3-6 words, suitable to add to a 'hard avoids' list, or null>",\n  "explanation": "<1 sentence explaining the pattern, or null>"\n}`;

    const anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": user.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 300,
        system: "You are a pattern-detection assistant. Return ONLY valid JSON, no preamble, no markdown.",
        messages: [{ role: "user", content: prompt }],
      }),
    });

    if (!anthropicRes.ok) {
      const body = await anthropicRes.text();
      console.error("Anthropic call failed:", anthropicRes.status, body);
      return res.status(502).json({ error: "Failed to analyze skip patterns" });
    }

    const anthropicData = await anthropicRes.json();
    const text = anthropicData.content?.[0]?.text?.trim() || "{}";
    const parsed = JSON.parse(text);

    return res.status(200).json({
      hasPattern: !!parsed.has_pattern,
      suggestedAvoid: parsed.suggested_avoid || null,
      explanation: parsed.explanation || null,
    });
  } catch (e) {
    console.error("suggest-avoids failed:", e);
    return res.status(500).json({ error: "Failed to analyze skip patterns" });
  }
}
