import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

const PAGE_SIZE = 25;

export default async function handler(req, res) {
  const { token, page, status } = req.query;
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  const pageNum = Math.max(parseInt(page, 10) || 0, 0);
  const from = pageNum * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;

  try {
    const supabase = getSupabaseAdmin();
    let query = supabase
      .from("seen_jobs")
      .select(
        "id, title, company_name, claude_score, claude_reasoning, salary_likely_above_floor, status, job_url, date_posted, created_at",
        { count: "exact" }
      )
      .eq("user_id", user.id);

    if (status) {
      query = query.eq("status", status);
    }

    const { data, error, count } = await query
      .order("claude_score", { ascending: false })
      .order("created_at", { ascending: false })
      .range(from, to);

    if (error) throw error;

    return res.status(200).json({
      jobs: data,
      page: pageNum,
      pageSize: PAGE_SIZE,
      total: count,
      hasMore: from + data.length < count,
    });
  } catch (e) {
    console.error("jobs endpoint failed:", e);
    return res.status(500).json({ error: "Request failed" });
  }
}
