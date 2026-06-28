import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

function normalize(text) {
  return (text || "").toLowerCase().trim().replace(/\s+/g, " ");
}

async function attachStats(supabase, userId, phrases) {
  if (phrases.length === 0) return phrases;

  const { data: jobs } = await supabase
    .from("seen_jobs")
    .select("search_phrase_id, claude_score, status")
    .eq("user_id", userId)
    .not("search_phrase_id", "is", null);

  const statsByPhrase = {};
  for (const job of jobs || []) {
    const id = job.search_phrase_id;
    if (!statsByPhrase[id]) {
      statsByPhrase[id] = { jobs_found: 0, score_sum: 0, score_count: 0, interested_or_applied: 0, skipped: 0 };
    }
    const s = statsByPhrase[id];
    s.jobs_found += 1;
    if (typeof job.claude_score === "number") {
      s.score_sum += job.claude_score;
      s.score_count += 1;
    }
    if (job.status === "interested" || job.status === "applied") s.interested_or_applied += 1;
    if (job.status === "skip") s.skipped += 1;
  }

  return phrases.map((p) => {
    const s = statsByPhrase[p.id];
    return {
      ...p,
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
        .from("search_phrases")
        .select("id, phrase, location, active, times_run, last_run_at")
        .eq("user_id", user.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      const withStats = await attachStats(supabase, user.id, data);
      return res.status(200).json({ phrases: withStats });
    }

    if (req.method === "POST") {
      const { phrase, location } = req.body || {};
      if (!phrase) return res.status(400).json({ error: "phrase is required" });

      const { data: existing } = await supabase
        .from("search_phrases")
        .select("id, phrase, location")
        .eq("user_id", user.id);
      const isDuplicate = (existing || []).some(
        (p) => normalize(p.phrase) === normalize(phrase) && normalize(p.location) === normalize(location)
      );
      if (isDuplicate) {
        return res.status(409).json({ error: "This phrase + location is already being tracked" });
      }

      const { error } = await supabase
        .from("search_phrases")
        .insert({ phrase, location: location || null, user_id: user.id, active: true });
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    if (req.method === "DELETE") {
      const { id } = req.body || {};
      if (!id) return res.status(400).json({ error: "id is required" });
      const { error } = await supabase
        .from("search_phrases")
        .delete()
        .eq("id", id)
        .eq("user_id", user.id);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    if (req.method === "PATCH") {
      const { id, active } = req.body || {};
      if (!id) return res.status(400).json({ error: "id is required" });
      const { error } = await supabase
        .from("search_phrases")
        .update({ active })
        .eq("id", id)
        .eq("user_id", user.id);
      if (error) throw error;
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "Method not allowed" });
  } catch (e) {
    console.error("phrases endpoint failed:", e);
    return res.status(500).json({ error: "Request failed" });
  }
}
