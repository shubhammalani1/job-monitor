import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token, anthropic_api_key, slack_webhook_url } = req.body || {};
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  const update = {};
  if (typeof anthropic_api_key === "string") update.anthropic_api_key = anthropic_api_key || null;
  if (typeof slack_webhook_url === "string") update.slack_webhook_url = slack_webhook_url || null;

  try {
    const supabase = getSupabaseAdmin();
    const { error } = await supabase.from("users").update(update).eq("id", user.id);
    if (error) throw error;
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("keys update failed:", e);
    return res.status(500).json({ error: "Failed to update keys" });
  }
}
