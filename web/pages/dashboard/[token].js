import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import styles from "../../styles/shared.module.css";

const EMPTY_PROFILE = {
  current_role: "",
  current_company: "",
  location: "",
  background: [],
  education: [],
  target_roles: [],
  target_location: "",
  hard_avoids: [],
  salary_floor_amount: "",
  salary_floor_currency: "",
};

function listToText(list) {
  return (list || []).join("\n");
}
function textToList(text) {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function Dashboard() {
  const router = useRouter();
  const { token } = router.query;

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [phrases, setPhrases] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [jobs, setJobs] = useState([]);

  const [anthropicKey, setAnthropicKey] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [newPhrase, setNewPhrase] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyUrl, setNewCompanyUrl] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [runningNow, setRunningNow] = useState(false);
  const [runNowError, setRunNowError] = useState("");

  useEffect(() => {
    if (!token) return;
    loadAll();
  }, [token]);

  async function loadAll() {
    setLoading(true);
    const userRes = await fetch(`/api/user?token=${token}`);
    if (!userRes.ok) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    const userData = await userRes.json();
    setUser(userData);
    setProfile({ ...EMPTY_PROFILE, ...userData.profile });

    const [phrasesRes, companiesRes, jobsRes] = await Promise.all([
      fetch(`/api/phrases?token=${token}`),
      fetch(`/api/companies?token=${token}`),
      fetch(`/api/jobs?token=${token}`),
    ]);
    setPhrases((await phrasesRes.json()).phrases || []);
    setCompanies((await companiesRes.json()).companies || []);
    setJobs((await jobsRes.json()).jobs || []);
    setLoading(false);
  }

  function flashSaved(msg) {
    setSavedMessage(msg);
    setTimeout(() => setSavedMessage(""), 2500);
  }

  async function saveProfile(e) {
    e.preventDefault();
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, profile }),
    });
    flashSaved("Profile saved");
  }

  async function saveKeys(e) {
    e.preventDefault();
    await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token,
        anthropic_api_key: anthropicKey || undefined,
        slack_webhook_url: slackWebhook || undefined,
      }),
    });
    setAnthropicKey("");
    setSlackWebhook("");
    flashSaved("Keys saved");
    loadAll();
  }

  async function runNow() {
    setRunningNow(true);
    setRunNowError("");
    try {
      const res = await fetch("/api/run-now", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRunNowError(data.error || "Failed to trigger run");
      } else {
        flashSaved("Run triggered - check back in a few minutes");
        loadAll();
      }
    } catch (e) {
      setRunNowError(e.message);
    } finally {
      setRunningNow(false);
    }
  }

  function cooldownRemainingMinutes() {
    if (!user?.last_manual_run_at) return 0;
    const elapsedMs = Date.now() - new Date(user.last_manual_run_at).getTime();
    const remainingMs = 10 * 60 * 1000 - elapsedMs;
    return remainingMs > 0 ? Math.ceil(remainingMs / 60000) : 0;
  }

  async function addPhrase(e) {
    e.preventDefault();
    if (!newPhrase.trim()) return;
    await fetch("/api/phrases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, phrase: newPhrase, location: newLocation || undefined }),
    });
    setNewPhrase("");
    setNewLocation("");
    loadAll();
  }

  async function togglePhrase(id, active) {
    await fetch("/api/phrases", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, id, active: !active }),
    });
    loadAll();
  }

  async function deletePhrase(id) {
    await fetch("/api/phrases", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, id }),
    });
    loadAll();
  }

  async function addCompany(e) {
    e.preventDefault();
    if (!newCompanyName.trim()) return;
    await fetch("/api/companies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, name: newCompanyName, careers_url: newCompanyUrl || undefined }),
    });
    setNewCompanyName("");
    setNewCompanyUrl("");
    loadAll();
  }

  async function toggleCompany(id, active) {
    await fetch("/api/companies", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, id, active: !active }),
    });
    loadAll();
  }

  async function deleteCompany(id) {
    await fetch("/api/companies", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, id }),
    });
    loadAll();
  }

  if (loading) return <div className={styles.page}>Loading...</div>;
  if (notFound) return <div className={styles.page}>Invalid or expired link.</div>;

  return (
    <div className={styles.page}>
      <div className={styles.dashboard}>
        <h1>Welcome, {user.name}</h1>
        {savedMessage && <div className={styles.toast}>{savedMessage}</div>}

        <section className={styles.section}>
          <h2>Run search now</h2>
          <p className={styles.subtitle}>
            Normally this runs automatically 3x/day. Use this to check right now instead of waiting
            for the next scheduled run.
          </p>
          <button type="button" onClick={runNow} disabled={runningNow || cooldownRemainingMinutes() > 0}>
            {runningNow
              ? "Triggering..."
              : cooldownRemainingMinutes() > 0
              ? `Wait ${cooldownRemainingMinutes()} min`
              : "Run now"}
          </button>
          {runNowError && <div className={styles.error}>{runNowError}</div>}
        </section>

        <section className={styles.section}>
          <h2>Your profile</h2>
          <p className={styles.subtitle}>This is what every job gets scored against.</p>
          <form onSubmit={saveProfile} className={styles.form}>
            <label>
              Current role
              <input
                value={profile.current_role}
                onChange={(e) => setProfile({ ...profile, current_role: e.target.value })}
              />
            </label>
            <label>
              Current company
              <input
                value={profile.current_company}
                onChange={(e) => setProfile({ ...profile, current_company: e.target.value })}
              />
            </label>
            <label>
              Location
              <input
                value={profile.location}
                onChange={(e) => setProfile({ ...profile, location: e.target.value })}
              />
            </label>
            <label>
              Background (one bullet per line)
              <textarea
                rows={5}
                value={listToText(profile.background)}
                onChange={(e) => setProfile({ ...profile, background: textToList(e.target.value) })}
              />
            </label>
            <label>
              Education (one per line)
              <textarea
                rows={2}
                value={listToText(profile.education)}
                onChange={(e) => setProfile({ ...profile, education: textToList(e.target.value) })}
              />
            </label>
            <label>
              Target roles (one per line, e.g. Strategy, Growth, Product)
              <textarea
                rows={3}
                value={listToText(profile.target_roles)}
                onChange={(e) => setProfile({ ...profile, target_roles: textToList(e.target.value) })}
              />
            </label>
            <label>
              Target location (e.g. Dubai/UAE)
              <input
                value={profile.target_location}
                onChange={(e) => setProfile({ ...profile, target_location: e.target.value })}
              />
            </label>
            <label>
              Hard avoids (one per line)
              <textarea
                rows={3}
                value={listToText(profile.hard_avoids)}
                onChange={(e) => setProfile({ ...profile, hard_avoids: textToList(e.target.value) })}
              />
            </label>
            <div className={styles.row}>
              <label>
                Salary floor amount
                <input
                  type="number"
                  value={profile.salary_floor_amount}
                  onChange={(e) => setProfile({ ...profile, salary_floor_amount: e.target.value })}
                />
              </label>
              <label>
                Currency
                <input
                  value={profile.salary_floor_currency}
                  onChange={(e) => setProfile({ ...profile, salary_floor_currency: e.target.value })}
                />
              </label>
            </div>
            <button type="submit">Save profile</button>
          </form>
        </section>

        <section className={styles.section}>
          <h2>Your API keys</h2>
          <p className={styles.subtitle}>
            Stored encrypted at rest in our database. Anthropic key:{" "}
            <strong>{user.has_anthropic_key ? "set" : "not set"}</strong>. Slack webhook:{" "}
            <strong>{user.has_slack_webhook ? "set" : "not set"}</strong>.
          </p>
          <form onSubmit={saveKeys} className={styles.form}>
            <label>
              Anthropic API key
              <input
                type="password"
                placeholder={user.has_anthropic_key ? "•••••••• (leave blank to keep)" : "sk-ant-..."}
                value={anthropicKey}
                onChange={(e) => setAnthropicKey(e.target.value)}
              />
            </label>
            <label>
              Slack webhook URL
              <input
                type="password"
                placeholder={user.has_slack_webhook ? "•••••••• (leave blank to keep)" : "https://hooks.slack.com/..."}
                value={slackWebhook}
                onChange={(e) => setSlackWebhook(e.target.value)}
              />
            </label>
            <button type="submit">Save keys</button>
          </form>
        </section>

        <section className={styles.section}>
          <h2>Search phrases</h2>
          <ul className={styles.list}>
            {phrases.map((p) => (
              <li key={p.id} className={styles.listItem}>
                <span style={{ opacity: p.active ? 1 : 0.4 }}>
                  {p.phrase} {p.location ? `— ${p.location}` : ""}
                </span>
                <span>
                  <button type="button" onClick={() => togglePhrase(p.id, p.active)}>
                    {p.active ? "Pause" : "Resume"}
                  </button>
                  <button type="button" onClick={() => deletePhrase(p.id)}>
                    Delete
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <form onSubmit={addPhrase} className={styles.inlineForm}>
            <input placeholder="e.g. product manager" value={newPhrase} onChange={(e) => setNewPhrase(e.target.value)} />
            <input placeholder="location (optional)" value={newLocation} onChange={(e) => setNewLocation(e.target.value)} />
            <button type="submit">Add phrase</button>
          </form>
        </section>

        <section className={styles.section}>
          <h2>Companies to watch</h2>
          <ul className={styles.list}>
            {companies.map((c) => (
              <li key={c.id} className={styles.listItem}>
                <span style={{ opacity: c.active ? 1 : 0.4 }}>
                  {c.name} {c.careers_url ? `— ${c.careers_url}` : ""}
                </span>
                <span>
                  <button type="button" onClick={() => toggleCompany(c.id, c.active)}>
                    {c.active ? "Pause" : "Resume"}
                  </button>
                  <button type="button" onClick={() => deleteCompany(c.id)}>
                    Delete
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <form onSubmit={addCompany} className={styles.inlineForm}>
            <input placeholder="Company name" value={newCompanyName} onChange={(e) => setNewCompanyName(e.target.value)} />
            <input placeholder="Careers page URL" value={newCompanyUrl} onChange={(e) => setNewCompanyUrl(e.target.value)} />
            <button type="submit">Add company</button>
          </form>
          <p className={styles.subtitle}>
            Note: careers page scraping isn't built per-company yet — adding a company here registers
            it, but it won't return jobs until a scraper is added for it.
          </p>
        </section>

        <section className={styles.section}>
          <h2>Jobs found ({jobs.length})</h2>
          <ul className={styles.jobList}>
            {jobs.map((j) => (
              <li key={j.id} className={styles.jobItem}>
                <div className={styles.jobHeader}>
                  <span className={styles.score}>{j.claude_score ?? 0}/100</span>
                  <a href={j.job_url} target="_blank" rel="noreferrer">
                    {j.title}
                  </a>
                  <span>— {j.company_name}</span>
                </div>
                {j.claude_reasoning && <p className={styles.reasoning}>{j.claude_reasoning}</p>}
              </li>
            ))}
            {jobs.length === 0 && <p className={styles.subtitle}>No jobs found yet. Check back after the next run.</p>}
          </ul>
        </section>
      </div>
    </div>
  );
}
