// Mirrors src/extract.py's approach: look for schema.org JobPosting JSON-LD
// (used by many job sites for Google Jobs indexing - Greenhouse, Attrax,
// LinkedIn, Indeed, and others all emit this), falling back to og:meta tags.

function stripHtml(html) {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function getMetaTags(html) {
  const tags = {};
  const metaTags = html.match(/<meta\s+[^>]*>/gi) || [];
  for (const tag of metaTags) {
    const propMatch = tag.match(/property=["']([^"']+)["']/i);
    const contentMatch = tag.match(/content=["']([^"']*)["']/i);
    if (propMatch && contentMatch) {
      tags[propMatch[1]] = contentMatch[1];
    }
  }
  return tags;
}

function extractFromHtml(html) {
  const scriptBlocks = html.match(/<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi) || [];

  for (const block of scriptBlocks) {
    const inner = block.replace(/^<script[^>]*>/i, "").replace(/<\/script>$/i, "");
    try {
      const data = JSON.parse(inner);
      const candidates = Array.isArray(data) ? data : [data];
      for (const candidate of candidates) {
        if (candidate && candidate["@type"] === "JobPosting") {
          return {
            title: candidate.title || null,
            company_name: candidate.hiringOrganization?.name || null,
            description: candidate.description ? stripHtml(candidate.description) : null,
          };
        }
      }
    } catch {
      // not valid JSON, skip this block
    }
  }

  const meta = getMetaTags(html);
  if (meta["og:title"] || meta["og:description"]) {
    return {
      title: meta["og:title"] || null,
      company_name: meta["og:site_name"] || null,
      description: meta["og:description"] || null,
    };
  }

  return null;
}

export async function fetchJobPosting(jobUrl) {
  try {
    const res = await fetch(jobUrl, {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    const html = await res.text();
    return extractFromHtml(html);
  } catch (e) {
    console.error("fetchJobPosting failed:", e);
    return null;
  }
}
