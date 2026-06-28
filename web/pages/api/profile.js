import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token, profile } = req.body || {};
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { error } = await supabase
      .from("users")
      .update({ profile })
      .eq("id", user.id);
    if (error) throw error;
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("profile update failed:", e);
    return res.status(500).json({ error: "Failed to update profile" });
  }
}
