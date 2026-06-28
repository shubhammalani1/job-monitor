import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

const VALID_STATUSES = ["new", "interested", "applied", "skip", "closed"];

export default async function handler(req, res) {
  if (req.method !== "PATCH") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token, id, status } = req.body || {};
  if (!id || !VALID_STATUSES.includes(status)) {
    return res.status(400).json({ error: "id and a valid status are required" });
  }

  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { error } = await supabase
      .from("seen_jobs")
      .update({ status })
      .eq("id", id)
      .eq("user_id", user.id);
    if (error) throw error;
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("job-status update failed:", e);
    return res.status(500).json({ error: "Failed to update job status" });
  }
}
