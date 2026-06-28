import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

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
        .select("id, phrase, location, active")
        .eq("user_id", user.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return res.status(200).json({ phrases: data });
    }

    if (req.method === "POST") {
      const { phrase, location } = req.body || {};
      if (!phrase) return res.status(400).json({ error: "phrase is required" });
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
