import { getSupabaseAdmin } from "../../../lib/supabaseAdmin";
import { verifyAdminToken } from "../../../lib/adminAuth";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { adminToken } = req.body || {};
  if (!verifyAdminToken(adminToken)) {
    return res.status(403).json({ error: "Invalid or expired admin session - re-enter your PIN" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data: users, error } = await supabase
      .from("users")
      .select("id, name, email, access_token, active, created_at, last_manual_run_at")
      .order("created_at", { ascending: true });
    if (error) throw error;

    const userIds = users.map((u) => u.id);
    const [phrasesRes, companiesRes, jobsRes] = await Promise.all([
      supabase.from("search_phrases").select("user_id").in("user_id", userIds),
      supabase.from("companies").select("user_id").in("user_id", userIds),
      supabase.from("seen_jobs").select("user_id").in("user_id", userIds),
    ]);

    const countBy = (rows) => {
      const map = {};
      for (const row of rows || []) {
        map[row.user_id] = (map[row.user_id] || 0) + 1;
      }
      return map;
    };
    const phraseCounts = countBy(phrasesRes.data);
    const companyCounts = countBy(companiesRes.data);
    const jobCounts = countBy(jobsRes.data);

    const enriched = users.map((u) => ({
      ...u,
      phrase_count: phraseCounts[u.id] || 0,
      company_count: companyCounts[u.id] || 0,
      job_count: jobCounts[u.id] || 0,
    }));

    return res.status(200).json({ users: enriched });
  } catch (e) {
    console.error("admin users list failed:", e);
    return res.status(500).json({ error: "Failed to load users" });
  }
}
