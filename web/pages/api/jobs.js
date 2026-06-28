import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

export default async function handler(req, res) {
  const token = req.query.token;
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data, error } = await supabase
      .from("seen_jobs")
      .select("id, title, company_name, claude_score, claude_reasoning, salary_likely_above_floor, status, job_url, date_posted, created_at")
      .eq("user_id", user.id)
      .order("claude_score", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(200);
    if (error) throw error;
    return res.status(200).json({ jobs: data });
  } catch (e) {
    console.error("jobs endpoint failed:", e);
    return res.status(500).json({ error: "Request failed" });
  }
}
