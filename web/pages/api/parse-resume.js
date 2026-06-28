import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";
import { extractTextFromFile } from "../../lib/resumeExtract";
import { parseClaudeJson } from "../../lib/parseClaudeJson";

export const config = {
  api: {
    bodyParser: { sizeLimit: "10mb" },
  },
};

const PROMPT = (resumeText) => `Here is a candidate's resume text:

${resumeText}

Extract whatever you can find into this exact JSON shape. Use null for anything not
findable in the resume - do not guess or invent values. "background" should be 4-8
bullet points summarizing experience/achievements in their own resume's terms.
Return ONLY valid JSON, no markdown, no preamble:
{
  "current_role": "<string or null>",
  "current_company": "<string or null>",
  "location": "<string or null>",
  "background": ["<bullet>", ...],
  "education": ["<degree/institution>", ...],
  "target_roles": ["<role type>", ...]
}`;

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token, filename, fileBase64 } = req.body || {};
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  if (!filename || !fileBase64) {
    return res.status(400).json({ error: "filename and fileBase64 are required" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data: settings } = await supabase.from("app_settings").select("anthropic_api_key").eq("id", 1).single();
    const anthropicApiKey = user.anthropic_api_key || settings?.anthropic_api_key;

    if (!anthropicApiKey) {
      return res.status(400).json({ error: "No Anthropic key available (yours or shared) to parse the resume" });
    }

    const buffer = Buffer.from(fileBase64, "base64");
    const resumeText = await extractTextFromFile(buffer, filename);

    const anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": anthropicApiKey,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 1000,
        system: "You are a resume parser. Return ONLY valid JSON, no preamble, no markdown.",
        messages: [{ role: "user", content: PROMPT(resumeText) }],
      }),
    });

    if (!anthropicRes.ok) {
      const body = await anthropicRes.text();
      console.error("Anthropic call failed:", anthropicRes.status, body);
      return res.status(502).json({ error: "Failed to parse resume" });
    }

    const anthropicData = await anthropicRes.json();
    const text = anthropicData.content?.[0]?.text || "{}";
    const parsed = parseClaudeJson(text);

    return res.status(200).json({ ok: true, profile: parsed });
  } catch (e) {
    console.error("parse-resume failed:", e);
    return res.status(500).json({ error: e.message || "Failed to parse resume" });
  }
}
