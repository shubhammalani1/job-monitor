import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

function normalize(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^\w\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function generateFingerprint(title, companyName) {
  const combined = `${normalize(title)}|${normalize(companyName)}`;
  return combined.slice(0, 64);
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token, title, company_name, job_url, notes } = req.body || {};
  if (!title || !company_name) {
    return res.status(400).json({ error: "title and company_name are required" });
  }

  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  const fingerprint = generateFingerprint(title, company_name);

  try {
    const supabase = getSupabaseAdmin();

    const { error: insertError } = await supabase.from("seen_jobs").upsert(
      {
        fingerprint,
        user_id: user.id,
        title,
        company_name,
        source_platform: "manual",
        status: "interested",
        job_url: job_url || null,
        raw_data: { manual: true, notes: notes || null },
      },
      { onConflict: "fingerprint,user_id", ignoreDuplicates: false }
    );
    if (insertError) throw insertError;

    const [phrasesRes, companiesRes] = await Promise.all([
      supabase.from("search_phrases").select("phrase").eq("user_id", user.id),
      supabase.from("companies").select("name").eq("user_id", user.id),
    ]);

    const existingPhrases = new Set((phrasesRes.data || []).map((p) => normalize(p.phrase)));
    const existingCompanies = new Set((companiesRes.data || []).map((c) => normalize(c.name)));

    const suggestPhrase = !existingPhrases.has(normalize(title)) ? title : null;
    const suggestCompany = !existingCompanies.has(normalize(company_name)) ? company_name : null;

    return res.status(200).json({ ok: true, suggestPhrase, suggestCompany });
  } catch (e) {
    console.error("add-job failed:", e);
    return res.status(500).json({ error: "Failed to add job" });
  }
}
