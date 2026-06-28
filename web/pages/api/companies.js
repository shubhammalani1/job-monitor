import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

function normalize(text) {
  return (text || "").toLowerCase().trim().replace(/\s+/g, " ");
}

async function attachStats(supabase, userId, companies) {
  if (companies.length === 0) return companies;

  const { data: jobs } = await supabase
    .from("seen_jobs")
    .select("company_id, claude_score, status")
    .eq("user_id", userId)
    .not("company_id", "is", null);

  const statsByCompany = {};
  for (const job of jobs || []) {
    const id = job.company_id;
    if (!statsByCompany[id]) {
      statsByCompany[id] = { jobs_found: 0, score_sum: 0, score_count: 0, interested_or_applied: 0, skipped: 0 };
    }
    const s = statsByCompany[id];
    s.jobs_found += 1;
    if (typeof job.claude_score === "number") {
      s.score_sum += job.claude_score;
      s.score_count += 1;
    }
    if (job.status === "interested" || job.status === "applied") s.interested_or_applied += 1;
    if (job.status === "skip") s.skipped += 1;
  }

  return companies.map((c) => {
    const s = statsByCompany[c.id];
    return {
      ...c,
      jobs_found: s?.jobs_found || 0,
      avg_score: s?.score_count ? Math.round(s.score_sum / s.score_count) : null,
      interested_or_applied: s?.interested_or_applied || 0,
      skipped: s?.skipped || 0,
    };
  });
}

export default async function handler(req, res) {
  const token = req.method === "GET" ? req.query.token : req.body?.token;
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  const supabase = getSupabaseAdmin();

  try {
    if (req.method === "GET") {
      const { data, error } = await supabase
        .from("companies")
        .select("id, name, careers_url, active, notes, times_run, last_run_at, detected_platform, run_times")
        .eq("user_id", user.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      const withStats = await attachStats(supabase, user.id, data);
      return res.status(200).json({ companies: withStats });
    }

    if (req.method === "POST") {
      const { name, careers_url, notes } = req.body || {};
      if (!name) return res.status(400).json({ error: "name is required" });

      const { data: existing } = await supabase.from("companies").select("name").eq("user_id", user.id);
      const isDuplicate = (existing || []).some((c) => normalize(c.name) === normalize(name));
      if (isDuplicate) {
        return res.status(409).json({ error: "This company is already being tracked" });
      }

      const { error } = await supabase
        .from("companies")
        .insert({ name, careers_url: careers_url || null, notes: notes || null, user_id: user.id, active: true });
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    if (req.method === "DELETE") {
      const { id } = req.body || {};
      if (!id) return res.status(400).json({ error: "id is required" });
      const { error } = await supabase
        .from("companies")
        .delete()
        .eq("id", id)
        .eq("user_id", user.id);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    if (req.method === "PATCH") {
      const { id, active, run_times } = req.body || {};
      if (!id) return res.status(400).json({ error: "id is required" });
      const update = {};
      if (active !== undefined) update.active = active;
      if (run_times !== undefined) update.run_times = run_times && run_times.length > 0 ? run_times : null;
      const { error } = await supabase
        .from("companies")
        .update(update)
        .eq("id", id)
        .eq("user_id", user.id);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "Method not allowed" });
  } catch (e) {
    console.error("companies endpoint failed:", e);
    return res.status(500).json({ error: "Request failed" });
  }
}
