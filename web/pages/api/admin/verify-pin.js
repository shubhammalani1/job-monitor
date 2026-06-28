import { getSupabaseAdmin } from "../../../lib/supabaseAdmin";
import { hashPin, createAdminToken } from "../../../lib/adminAuth";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { pin } = req.body || {};
  if (!pin) {
    return res.status(400).json({ error: "PIN is required" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data: settings, error } = await supabase.from("app_settings").select("pin_hash").eq("id", 1).single();
    if (error) throw error;

    if (!settings?.pin_hash) {
      return res.status(409).json({ error: "No PIN has been set yet", needsSetup: true });
    }

    if (hashPin(pin) !== settings.pin_hash) {
      return res.status(403).json({ error: "Incorrect PIN" });
    }

    return res.status(200).json({ ok: true, adminToken: createAdminToken() });
  } catch (e) {
    console.error("verify-pin failed:", e);
    return res.status(500).json({ error: "Failed to verify PIN" });
  }
}
