import { createClient } from "@supabase/supabase-js";

// Server-side only. Never import this from a page component or anything
// that ships to the browser - it holds the service_role key.
let client = null;

export function getSupabaseAdmin() {
  if (!client) {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!url || !key) {
      throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars");
    }
    client = createClient(url, key);
  }
  return client;
}

export async function getUserByToken(token) {
  if (!token) return null;
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from("users")
    .select("*")
    .eq("access_token", token)
    .single();
  if (error) return null;
  return data;
}
