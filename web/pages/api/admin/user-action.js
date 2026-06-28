import crypto from "crypto";
import { getSupabaseAdmin } from "../../../lib/supabaseAdmin";
import { verifyAdminToken } from "../../../lib/adminAuth";

const VALID_ACTIONS = ["delete", "regenerate_token", "clear_data", "toggle_active"];

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { adminToken, userId, action } = req.body || {};
  if (!verifyAdminToken(adminToken)) {
    return res.status(403).json({ error: "Invalid or expired admin session - re-enter your PIN" });
  }
  if (!userId || !VALID_ACTIONS.includes(action)) {
    return res.status(400).json({ error: "userId and a valid action are required" });
  }

  const supabase = getSupabaseAdmin();

  try {
    if (action === "delete") {
      await supabase.from("search_phrases").delete().eq("user_id", userId);
      await supabase.from("companies").delete().eq("user_id", userId);
      await supabase.from("seen_jobs").delete().eq("user_id", userId);
      await supabase.from("run_logs").delete().eq("user_id", userId);
      const { error } = await supabase.from("users").delete().eq("id", userId);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    if (action === "regenerate_token") {
      const newToken = crypto.randomBytes(32).toString("hex");
      const { error } = await supabase.from("users").update({ access_token: newToken }).eq("id", userId);
      if (error) throw error;
      return res.status(200).json({ ok: true, access_token: newToken });
    }

    if (action === "clear_data") {
      await supabase.from("seen_jobs").delete().eq("user_id", userId);
      await supabase.from("run_logs").delete().eq("user_id", userId);
      return res.status(200).json({ ok: true });
    }

    if (action === "toggle_active") {
      const { data: current, error: fetchError } = await supabase
        .from("users")
        .select("active")
        .eq("id", userId)
        .single();
      if (fetchError) throw fetchError;
      const { error } = await supabase.from("users").update({ active: !current.active }).eq("id", userId);
      if (error) throw error;
      return res.status(200).json({ ok: true, active: !current.active });
    }
  } catch (e) {
    console.error(`admin user-action '${action}' failed:`, e);
    return res.status(500).json({ error: "Action failed" });
  }
}
