import { getUserByToken } from "../../lib/supabaseAdmin";

export default async function handler(req, res) {
  const { token } = req.query;
  const user = await getUserByToken(token);
  if (!user) {
    return res.status(404).json({ error: "Invalid token" });
  }

  // Mask secrets - only tell the frontend whether they're set, never their value.
  return res.status(200).json({
    id: user.id,
    name: user.name,
    email: user.email,
    profile: user.profile,
    active: user.active,
    has_anthropic_key: !!user.anthropic_api_key,
    has_slack_webhook: !!user.slack_webhook_url,
    last_manual_run_at: user.last_manual_run_at,
  });
}
