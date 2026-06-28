import { getSupabaseAdmin } from "../../../lib/supabaseAdmin";
import { verifyAdminToken } from "../../../lib/adminAuth";

const EDITABLE_FIELDS = [
  "anthropic_api_key",
  "jsearch_api_key",
  "paused",
  "run_times",
  "company_run_times",
  "jsearch_quota_limit",
  "jsearch_period_reset_at",
];

export default async function handler(req, res) {
  const supabase = getSupabaseAdmin();

  if (req.method === "GET") {
    try {
      const { data, error } = await supabase.from("app_settings").select("*").eq("id", 1).single();
      if (error) throw error;
      return res.status(200).json({
        paused: data.paused,
        run_times: data.run_times,
        company_run_times: data.company_run_times,
        jsearch_quota_limit: data.jsearch_quota_limit,
        jsearch_calls_this_period: data.jsearch_calls_this_period,
        jsearch_period_reset_at: data.jsearch_period_reset_at,
        has_anthropic_key: !!data.anthropic_api_key,
        has_jsearch_key: !!data.jsearch_api_key,
        pin_set: !!data.pin_hash,
      });
    } catch (e) {
      console.error("admin settings GET failed:", e);
      return res.status(500).json({ error: "Failed to load settings" });
    }
  }

  if (req.method === "POST") {
    const { adminToken, ...updates } = req.body || {};
    if (!verifyAdminToken(adminToken)) {
      return res.status(403).json({ error: "Invalid or expired admin session - re-enter your PIN" });
    }

    const filteredUpdates = {};
    for (const key of EDITABLE_FIELDS) {
      if (key in updates && updates[key] !== undefined) {
        filteredUpdates[key] = updates[key] === "" ? null : updates[key];
      }
    }

    if (Object.keys(filteredUpdates).length === 0) {
      return res.status(400).json({ error: "No valid fields to update" });
    }

    try {
      const { error } = await supabase
        .from("app_settings")
        .update({ ...filteredUpdates, updated_at: new Date().toISOString() })
        .eq("id", 1);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    } catch (e) {
      console.error("admin settings POST failed:", e);
      return res.status(500).json({ error: "Failed to update settings" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}
