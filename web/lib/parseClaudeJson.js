// Claude is instructed to return raw JSON, but sometimes wraps it in markdown
// code fences anyway - strip those before parsing instead of failing outright.
export function parseClaudeJson(text) {
  const trimmed = (text || "").trim();
  const fenceMatch = trimmed.match(/^```(?:json)?\s*\n?([\s\S]*?)\n?```$/);
  const jsonText = fenceMatch ? fenceMatch[1].trim() : trimmed;
  return JSON.parse(jsonText || "{}");
}
