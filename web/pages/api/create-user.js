import { getSupabaseAdmin } from "../../lib/supabaseAdmin";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { name, email } = req.body || {};
  if (!name) {
    return res.status(400).json({ error: "name is required" });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data, error } = await supabase
      .from("users")
      .insert({ name, email: email || null, profile: {}, active: true })
      .select("access_token")
      .single();

    if (error) throw error;

    return res.status(200).json({ access_token: data.access_token });
  } catch (e) {
    console.error("create-user failed:", e);
    return res.status(500).json({ error: "Failed to create user" });
  }
}
