import { getSupabaseAdmin, getUserByToken } from "../../lib/supabaseAdmin";

const COOLDOWN_MINUTES = 10;
const GITHUB_OWNER = "shubhammalani1";
const GITHUB_REPO = "job-monitor";
const WORKFLOW_FILE = "monitor.yml";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { token } = req.body || {};
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  if (user.last_manual_run_at) {
    const elapsedMs = Date.now() - new Date(user.last_manual_run_at).getTime();
    const remainingMs = COOLDOWN_MINUTES * 60 * 1000 - elapsedMs;
    if (remainingMs > 0) {
      return res.status(429).json({
        error: `Please wait ${Math.ceil(remainingMs / 60000)} more minute(s) before running again`,
      });
    }
  }

  const githubToken = process.env.GITHUB_DISPATCH_TOKEN;
  if (!githubToken) {
    return res.status(500).json({ error: "Run-now is not configured on the server" });
  }

  try {
    const dispatchRes = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main", inputs: { user_id: user.id } }),
      }
    );

    if (!dispatchRes.ok) {
      const body = await dispatchRes.text();
      console.error("GitHub dispatch failed:", dispatchRes.status, body);
      return res.status(502).json({ error: "Failed to trigger run" });
    }

    const supabase = getSupabaseAdmin();
    await supabase
      .from("users")
      .update({ last_manual_run_at: new Date().toISOString() })
      .eq("id", user.id);

    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("run-now failed:", e);
    return res.status(500).json({ error: "Failed to trigger run" });
  }
}
