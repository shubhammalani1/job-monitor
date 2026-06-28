import { getSupabaseAdmin } from "../../../lib/supabaseAdmin";
import { hashPin } from "../../../lib/adminAuth";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { newPin, currentPin } = req.body || {};
  if (!newPin || newPin.length < 4) {
    return res.status(400).json({ error: "PIN must be at least 4 characters" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data: settings } = await supabase.from("app_settings").select("pin_hash").eq("id", 1).single();

    if (settings?.pin_hash) {
      if (!currentPin || hashPin(currentPin) !== settings.pin_hash) {
        return res.status(403).json({ error: "Current PIN is incorrect" });
      }
    }

    const { error } = await supabase.from("app_settings").update({ pin_hash: hashPin(newPin) }).eq("id", 1);
    if (error) throw error;

    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("set-pin failed:", e);
    return res.status(500).json({ error: "Failed to set PIN" });
  }
}
