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

const TABS = [
  { id: "jobs", label: "Jobs" },
  { id: "search", label: "Search setup" },
  { id: "profile", label: "Profile" },
  { id: "settings", label: "Settings" },
];

function listToText(list) {
  return (list || []).join("\n");
}
function textToList(text) {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function scoreClass(score) {
  if (score >= 70) return styles.scoreHigh;
  if (score >= 50) return styles.scoreMid;
  return styles.scoreLow;
}

function formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return null;
  }
}

export default function Dashboard() {
  const router = useRouter();
  const { token } = router.query;

  const [activeTab, setActiveTab] = useState("jobs");
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [phrases, setPhrases] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [jobsPage, setJobsPage] = useState(0);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsHasMore, setJobsHasMore] = useState(false);
  const [jobsStatusFilter, setJobsStatusFilter] = useState("");
  const [showLowScore, setShowLowScore] = useState(false);

  const [anthropicKey, setAnthropicKey] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [newPhrase, setNewPhrase] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyUrl, setNewCompanyUrl] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [runningNow, setRunningNow] = useState(false);
  const [runNowError, setRunNowError] = useState("");
  const [skipPromptId, setSkipPromptId] = useState(null);
  const [skipReasonText, setSkipReasonText] = useState("");
  const [newJobTitle, setNewJobTitle] = useState("");
  const [newJobCompany, setNewJobCompany] = useState("");
  const [newJobUrl, setNewJobUrl] = useState("");
  const [newJobNotes, setNewJobNotes] = useState("");
  const [addJobError, setAddJobError] = useState("");
  const [addJobSuggestion, setAddJobSuggestion] = useState(null);
  const [needsManualEntry, setNeedsManualEntry] = useState(false);
  const [addJobLoading, setAddJobLoading] = useState(false);
  const [patternResult, setPatternResult] = useState(null);
  const [patternLoading, setPatternLoading] = useState(false);
  const [patternError, setPatternError] = useState("");

  const [platformStatus, setPlatformStatus] = useState(null);
  const [adminToken, setAdminToken] = useState(null);
  const [pinInput, setPinInput] = useState("");
  const [pinError, setPinError] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [newPinInput, setNewPinInput] = useState("");
  const [platformForm, setPlatformForm] = useState({
    anthropic_api_key: "",
    jsearch_api_key: "",
    paused: false,
    run_times: "",
    jsearch_quota_limit: 200,
  });
  const [platformMessage, setPlatformMessage] = useState("");
  const [platformError, setPlatformError] = useState("");
  const [adminUsers, setAdminUsers] = useState(null);
  const [adminUsersError, setAdminUsersError] = useState("");
  const [adminUserActionError, setAdminUserActionError] = useState("");
  const [revealedLinkIds, setRevealedLinkIds] = useState([]);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [selectedPhraseIds, setSelectedPhraseIds] = useState([]);
  const [selectedCompanyIds, setSelectedCompanyIds] = useState([]);
  const [targetedRunLoading, setTargetedRunLoading] = useState(false);
  const [targetedRunError, setTargetedRunError] = useState("");

  useEffect(() => {
    if (!token) return;
    loadAll();
    loadPlatformStatus();
  }, [token]);

  // Forces a re-render every 15s so the "Wait X min" cooldown countdown actually
  // ticks down instead of freezing at whatever value was shown on the last render.
  const [, setCooldownTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setCooldownTick((t) => t + 1), 15000);
    return () => clearInterval(interval);
  }, []);

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

    const [phrasesRes, companiesRes] = await Promise.all([
      fetch(`/api/phrases?token=${token}`),
      fetch(`/api/companies?token=${token}`),
    ]);
    setPhrases((await phrasesRes.json()).phrases || []);
    setCompanies((await companiesRes.json()).companies || []);
    await loadJobs(0, jobsStatusFilter);
    setLoading(false);
  }

  async function loadJobs(page, statusFilter, showLowOverride) {
    const showLow = showLowOverride !== undefined ? showLowOverride : showLowScore;
    const params = new URLSearchParams({ token, page: String(page) });
    if (statusFilter) params.set("status", statusFilter);
    // Only apply the relevance floor on the unfiltered "All" view - if someone
    // explicitly filters by status (e.g. Skip), show everything regardless of score.
    if (!showLow && !statusFilter) params.set("minScore", "40");
    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    setJobs(data.jobs || []);
    setJobsPage(data.page || 0);
    setJobsTotal(data.total || 0);
    setJobsHasMore(!!data.hasMore);
  }

  function toggleShowLowScore() {
    const next = !showLowScore;
    setShowLowScore(next);
    loadJobs(0, jobsStatusFilter, next);
  }

  async function setJobStatus(jobId, status, reason) {
    await fetch("/api/job-status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, id: jobId, status, reason }),
    });
    loadJobs(jobsPage, jobsStatusFilter);
  }

  function openSkipPrompt(jobId) {
    setSkipPromptId(jobId);
    setSkipReasonText("");
  }

  async function confirmSkip(jobId) {
    await setJobStatus(jobId, "skip", skipReasonText);
    setSkipPromptId(null);
  }

  async function addManualJob(e) {
    e.preventDefault();
    setAddJobError("");
    setAddJobLoading(true);
    try {
      const res = await fetch("/api/add-job", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          job_url: newJobUrl || undefined,
          title: newJobTitle || undefined,
          company_name: newJobCompany || undefined,
          notes: newJobNotes || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAddJobError(data.error || "Failed to add job");
        if (data.needsManualEntry) setNeedsManualEntry(true);
        return;
      }
      setAddJobSuggestion({ phrase: data.suggestPhrase, company: data.suggestCompany });
      setNeedsManualEntry(false);
      setNewJobTitle("");
      setNewJobCompany("");
      setNewJobUrl("");
      setNewJobNotes("");
      flashSaved("Job added and marked interested");
      loadJobs(0, jobsStatusFilter);
    } catch (err) {
      setAddJobError(err.message);
    } finally {
      setAddJobLoading(false);
    }
  }

  async function acceptPhraseSuggestion() {
    await fetch("/api/phrases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, phrase: addJobSuggestion.phrase }),
    });
    setAddJobSuggestion({ ...addJobSuggestion, phrase: null });
    loadAll();
  }

  async function acceptCompanySuggestion() {
    await fetch("/api/companies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, name: addJobSuggestion.company }),
    });
    setAddJobSuggestion({ ...addJobSuggestion, company: null });
    loadAll();
  }

  function changeStatusFilter(status) {
    setJobsStatusFilter(status);
    loadJobs(0, status);
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

  function handleResumeUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setResumeLoading(true);
    setResumeError("");

    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const base64 = reader.result.split(",")[1];
        const res = await fetch("/api/parse-resume", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, filename: file.name, fileBase64: base64 }),
        });
        const data = await res.json();
        if (!res.ok) {
          setResumeError(data.error || "Failed to parse resume");
          return;
        }
        const extracted = data.profile || {};
        setProfile((p) => ({
          ...p,
          current_role: extracted.current_role || p.current_role,
          current_company: extracted.current_company || p.current_company,
          location: extracted.location || p.location,
          background: extracted.background?.length ? extracted.background : p.background,
          education: extracted.education?.length ? extracted.education : p.education,
          target_roles: extracted.target_roles?.length ? extracted.target_roles : p.target_roles,
        }));
        flashSaved("Resume parsed - review the fields below, then save");
      } catch (err) {
        setResumeError(err.message);
      } finally {
        setResumeLoading(false);
        e.target.value = "";
      }
    };
    reader.onerror = () => {
      setResumeError("Failed to read file");
      setResumeLoading(false);
    };
    reader.readAsDataURL(file);
  }

  async function checkSkipPatterns() {
    setPatternLoading(true);
    setPatternError("");
    setPatternResult(null);
    try {
      const res = await fetch("/api/suggest-avoids", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      if (!res.ok) {
        setPatternError(data.error || "Failed to check for patterns");
        return;
      }
      setPatternResult(data);
    } catch (err) {
      setPatternError(err.message);
    } finally {
      setPatternLoading(false);
    }
  }

  async function acceptPatternSuggestion() {
    const updatedProfile = {
      ...profile,
      hard_avoids: [...(profile.hard_avoids || []), patternResult.suggestedAvoid],
    };
    setProfile(updatedProfile);
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, profile: updatedProfile }),
    });
    setPatternResult(null);
    flashSaved(`Added "${patternResult.suggestedAvoid}" to your hard avoids`);
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

  async function loadPlatformStatus() {
    try {
      const res = await fetch("/api/admin/settings");
      const data = await res.json();
      if (res.ok) {
        setPlatformStatus(data);
        setPlatformForm((f) => ({
          ...f,
          paused: data.paused,
          run_times: (data.run_times || []).join(", "),
          jsearch_quota_limit: data.jsearch_quota_limit,
        }));
      }
    } catch {
      // platform status is non-critical, fail silently
    }
  }

  async function submitPin() {
    setPinLoading(true);
    setPinError("");
    try {
      const res = await fetch("/api/admin/verify-pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pinInput }),
      });
      const data = await res.json();
      if (!res.ok) {
        setPinError(data.error || "Failed to verify PIN");
        return;
      }
      setAdminToken(data.adminToken);
      setPinInput("");
      loadAdminUsers(data.adminToken);
    } catch (err) {
      setPinError(err.message);
    } finally {
      setPinLoading(false);
    }
  }

  async function loadAdminUsers(tokenOverride) {
    setAdminUsersError("");
    try {
      const res = await fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adminToken: tokenOverride || adminToken }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAdminUsersError(data.error || "Failed to load users");
        return;
      }
      setAdminUsers(data.users);
    } catch (err) {
      setAdminUsersError(err.message);
    }
  }

  async function runAdminUserAction(userId, action, confirmMessage) {
    if (confirmMessage && !window.confirm(confirmMessage)) return;
    setAdminUserActionError("");
    try {
      const res = await fetch("/api/admin/user-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adminToken, userId, action }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAdminUserActionError(data.error || "Action failed");
        return;
      }
      if (action === "regenerate_token") {
        setRevealedLinkIds((ids) => (ids.includes(userId) ? ids : [...ids, userId]));
      }
      loadAdminUsers();
    } catch (err) {
      setAdminUserActionError(err.message);
    }
  }

  function toggleLinkReveal(userId) {
    setRevealedLinkIds((ids) => (ids.includes(userId) ? ids.filter((id) => id !== userId) : [...ids, userId]));
  }

  function copyLink(accessToken) {
    const link = `${window.location.origin}/dashboard/${accessToken}`;
    navigator.clipboard.writeText(link);
    flashSaved("Link copied");
  }

  async function submitNewPin() {
    setPinLoading(true);
    setPinError("");
    try {
      const res = await fetch("/api/admin/set-pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ newPin: newPinInput, currentPin: pinInput || undefined }),
      });
      const data = await res.json();
      if (!res.ok) {
        setPinError(data.error || "Failed to set PIN");
        return;
      }
      setNewPinInput("");
      setPinInput("");
      flashSaved("PIN set");
      loadPlatformStatus();
    } catch (err) {
      setPinError(err.message);
    } finally {
      setPinLoading(false);
    }
  }

  async function savePlatformSettings() {
    setPlatformError("");
    try {
      const res = await fetch("/api/admin/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          adminToken,
          anthropic_api_key: platformForm.anthropic_api_key || undefined,
          jsearch_api_key: platformForm.jsearch_api_key || undefined,
          paused: platformForm.paused,
          run_times: platformForm.run_times
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
          jsearch_quota_limit: parseInt(platformForm.jsearch_quota_limit, 10) || 200,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setPlatformError(data.error || "Failed to save platform settings");
        return;
      }
      setPlatformForm((f) => ({ ...f, anthropic_api_key: "", jsearch_api_key: "" }));
      flashSaved("Platform settings saved");
      loadPlatformStatus();
    } catch (err) {
      setPlatformError(err.message);
    }
  }

  function lockPlatformSettings() {
    setAdminToken(null);
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

  function togglePhraseSelection(id) {
    setSelectedPhraseIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]));
  }

  function toggleCompanySelection(id) {
    setSelectedCompanyIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]));
  }

  async function runSelectedOnly() {
    setTargetedRunLoading(true);
    setTargetedRunError("");
    try {
      const res = await fetch("/api/run-now", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, phraseIds: selectedPhraseIds, companyIds: selectedCompanyIds }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTargetedRunError(data.error || "Failed to trigger run");
      } else {
        flashSaved(`Run triggered for ${selectedPhraseIds.length} phrase(s) and ${selectedCompanyIds.length} company(ies)`);
        setSelectedPhraseIds([]);
        setSelectedCompanyIds([]);
        loadAll();
      }
    } catch (e) {
      setTargetedRunError(e.message);
    } finally {
      setTargetedRunLoading(false);
    }
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

  if (loading) return <div className={styles.page}><div className={styles.dashboard}>Loading...</div></div>;
  if (notFound) return <div className={styles.page}><div className={styles.dashboard}>Invalid or expired link.</div></div>;

  return (
    <div className={styles.page}>
      <div className={styles.dashboard}>
        <div className={styles.topBar}>
          <div className={styles.brand}>
            <span className={styles.brandDot} />
            Job Monitor
          </div>
          <button type="button" onClick={runNow} disabled={runningNow || cooldownRemainingMinutes() > 0}>
            {runningNow
              ? "Triggering..."
              : cooldownRemainingMinutes() > 0
              ? `Wait ${cooldownRemainingMinutes()} min`
              : "Run now"}
          </button>
        </div>

        {savedMessage && <div className={styles.toast}>{savedMessage}</div>}
        {runNowError && <div className={styles.error} style={{ marginBottom: 16 }}>{runNowError}</div>}

        <div className={styles.tabRow}>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={activeTab === t.id ? styles.tabButtonActive : styles.tabButton}
              onClick={() => setActiveTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {activeTab === "jobs" && (
          <>
            <section className={styles.section}>
              <h2>Found a job elsewhere?</h2>
              <p className={styles.subtitle}>
                Paste the link and it'll pull the title, company, and description automatically,
                mark it interested, and suggest tracking that title or company going forward.
              </p>
              <form onSubmit={addManualJob} className={styles.inlineForm} style={{ flexWrap: "wrap" }}>
                <input
                  placeholder="Paste a job posting link"
                  value={newJobUrl}
                  onChange={(e) => setNewJobUrl(e.target.value)}
                  required={!needsManualEntry}
                  style={{ flex: 2, minWidth: 220 }}
                />
                <button type="submit" disabled={addJobLoading}>
                  {addJobLoading ? "Reading..." : "Add job"}
                </button>
              </form>
              {needsManualEntry && (
                <form onSubmit={addManualJob} className={styles.inlineForm} style={{ flexWrap: "wrap", marginTop: 10 }}>
                  <input placeholder="Job title" value={newJobTitle} onChange={(e) => setNewJobTitle(e.target.value)} required />
                  <input placeholder="Company" value={newJobCompany} onChange={(e) => setNewJobCompany(e.target.value)} required />
                  <button type="submit" disabled={addJobLoading}>
                    Add with these details
                  </button>
                </form>
              )}
              {addJobError && <div className={styles.error} style={{ marginTop: 10 }}>{addJobError}</div>}
              {addJobSuggestion && (addJobSuggestion.phrase || addJobSuggestion.company) && (
                <div className={styles.toast} style={{ display: "block", marginTop: 12 }}>
                  {addJobSuggestion.phrase && (
                    <div style={{ marginBottom: 6 }}>
                      Track "{addJobSuggestion.phrase}" as a search phrase too?{" "}
                      <button type="button" onClick={acceptPhraseSuggestion}>
                        Yes, add it
                      </button>
                    </div>
                  )}
                  {addJobSuggestion.company && (
                    <div>
                      Track "{addJobSuggestion.company}" as a company too?{" "}
                      <button type="button" onClick={acceptCompanySuggestion}>
                        Yes, add it
                      </button>
                    </div>
                  )}
                </div>
              )}
            </section>

            <section className={styles.section}>
            <div className={styles.sectionHeadRow}>
              <h2>Jobs found ({jobsTotal})</h2>
              {!jobsStatusFilter && (
                <button type="button" onClick={toggleShowLowScore} className={styles.filterInactive}>
                  {showLowScore ? "Hide low-relevance jobs" : "Show low-relevance jobs"}
                </button>
              )}
            </div>
            {!jobsStatusFilter && !showLowScore && (
              <p className={styles.subtitle} style={{ marginTop: -4 }}>
                Jobs scored below 40 are hidden by default - they're still saved so they
                won't be rescored, just kept off this view.
              </p>
            )}
            <div className={styles.filterRow}>
              {["", "new", "interested", "applied", "skip", "closed"].map((s) => (
                <button
                  key={s || "all"}
                  type="button"
                  onClick={() => changeStatusFilter(s)}
                  className={jobsStatusFilter === s ? styles.filterActive : styles.filterInactive}
                >
                  {s || "all"}
                </button>
              ))}
            </div>
            <ul className={styles.jobList}>
              {jobs.map((j) => (
                <li key={j.id} className={styles.jobItem}>
                  <div className={styles.jobHeader}>
                    <span className={`${styles.scoreBadge} ${scoreClass(j.claude_score ?? 0)}`}>
                      {j.claude_score ?? 0}
                    </span>
                    <a href={j.job_url} target="_blank" rel="noreferrer" className={styles.jobTitleLink}>
                      {j.title}
                    </a>
                    <span className={styles.jobCompany}>{j.company_name}</span>
                    {formatDate(j.date_posted) && (
                      <span className={styles.jobCompany}>· {formatDate(j.date_posted)}</span>
                    )}
                  </div>
                  {j.claude_reasoning && <p className={styles.reasoning}>{j.claude_reasoning}</p>}
                  {j.skip_reason && <p className={styles.reasoning}>Skip reason: {j.skip_reason}</p>}
                  <div className={styles.statusRow}>
                    <span className={styles.statusPill}>{j.status}</span>
                    {["interested", "applied"].map((s) => (
                      <button key={s} type="button" disabled={j.status === s} onClick={() => setJobStatus(j.id, s)}>
                        {s}
                      </button>
                    ))}
                    <button type="button" disabled={j.status === "skip"} onClick={() => openSkipPrompt(j.id)}>
                      skip
                    </button>
                  </div>
                  {skipPromptId === j.id && (
                    <div className={styles.inlineForm} style={{ marginTop: 10 }}>
                      <input
                        placeholder="Why skip this? (optional)"
                        value={skipReasonText}
                        onChange={(e) => setSkipReasonText(e.target.value)}
                      />
                      <button type="button" onClick={() => confirmSkip(j.id)}>
                        Confirm skip
                      </button>
                      <button type="button" onClick={() => setSkipPromptId(null)}>
                        Cancel
                      </button>
                    </div>
                  )}
                </li>
              ))}
              {jobs.length === 0 && (
                <div className={styles.emptyState}>No jobs found yet. Check back after the next run.</div>
              )}
            </ul>
            <div className={styles.pagerRow}>
              <button type="button" disabled={jobsPage === 0} onClick={() => loadJobs(jobsPage - 1, jobsStatusFilter)}>
                Previous
              </button>
              <span className={styles.subtitle} style={{ margin: 0 }}>
                Page {jobsPage + 1}
              </span>
              <button type="button" disabled={!jobsHasMore} onClick={() => loadJobs(jobsPage + 1, jobsStatusFilter)}>
                Next
              </button>
            </div>
            </section>
          </>
        )}

        {activeTab === "search" && (
          <>
            {(selectedPhraseIds.length > 0 || selectedCompanyIds.length > 0) && (
              <section className={styles.section} style={{ position: "sticky", top: 10, zIndex: 5 }}>
                <p className={styles.subtitle} style={{ margin: 0, marginBottom: 8 }}>
                  {selectedPhraseIds.length} phrase(s), {selectedCompanyIds.length} company(ies) selected
                </p>
                <button type="button" onClick={runSelectedOnly} disabled={targetedRunLoading || cooldownRemainingMinutes() > 0}>
                  {targetedRunLoading
                    ? "Triggering..."
                    : cooldownRemainingMinutes() > 0
                    ? `Wait ${cooldownRemainingMinutes()} min`
                    : "Run selected only"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedPhraseIds([]);
                    setSelectedCompanyIds([]);
                  }}
                >
                  Clear selection
                </button>
                {targetedRunError && <div className={styles.error} style={{ marginTop: 8 }}>{targetedRunError}</div>}
              </section>
            )}

            <section className={styles.section}>
              <h2>Search phrases</h2>
              <p className={styles.subtitle}>
                Phrases JSearch will look for, on schedule. Check a few and use "Run selected only" above to test
                just those without running everything.
              </p>
              <ul className={styles.list}>
                {phrases.map((p) => (
                  <li key={p.id} className={styles.listItem}>
                    <span style={{ opacity: p.active ? 1 : 0.4 }}>
                      <input
                        type="checkbox"
                        checked={selectedPhraseIds.includes(p.id)}
                        onChange={() => togglePhraseSelection(p.id)}
                        style={{ marginRight: 8 }}
                      />
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
                      <input
                        type="checkbox"
                        checked={selectedCompanyIds.includes(c.id)}
                        onChange={() => toggleCompanySelection(c.id)}
                        style={{ marginRight: 8 }}
                      />
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
              <p className={styles.subtitle} style={{ marginTop: 12, marginBottom: 0 }}>
                Works automatically for companies on Greenhouse (boards.greenhouse.io/...), Lever
                (jobs.lever.co/...), or Attrax-powered career sites (e.g. careers.deliveryhero.com).
                Other career pages aren't supported yet.
              </p>
            </section>
          </>
        )}

        {activeTab === "profile" && (
          <>
            <section className={styles.section}>
              <h2>Upload your resume (optional)</h2>
              <p className={styles.subtitle}>
                Auto-fills the fields below from a PDF, DOCX, or text resume - review and edit
                before saving, nothing is saved automatically.
              </p>
              <input type="file" accept=".pdf,.docx,.txt" onChange={handleResumeUpload} disabled={resumeLoading} />
              {resumeLoading && <p className={styles.subtitle} style={{ marginTop: 8 }}>Reading resume...</p>}
              {resumeError && <div className={styles.error} style={{ marginTop: 10 }}>{resumeError}</div>}
            </section>

            <section className={styles.section}>
              <h2>Spot a pattern in what you skip?</h2>
              <p className={styles.subtitle}>
                Looks at jobs you've skipped with a reason given, and checks whether they share a
                theme worth adding to your hard avoids below.
              </p>
              <button type="button" onClick={checkSkipPatterns} disabled={patternLoading}>
                {patternLoading ? "Checking..." : "Check my skipped jobs for patterns"}
              </button>
              {patternError && <div className={styles.error} style={{ marginTop: 10 }}>{patternError}</div>}
              {patternResult && !patternResult.hasPattern && (
                <p className={styles.subtitle} style={{ marginTop: 10, marginBottom: 0 }}>
                  {patternResult.message || "No clear recurring pattern found yet."}
                </p>
              )}
              {patternResult && patternResult.hasPattern && (
                <div className={styles.toast} style={{ display: "block", marginTop: 12 }}>
                  <div style={{ marginBottom: 6 }}>{patternResult.explanation}</div>
                  <div>
                    Add "{patternResult.suggestedAvoid}" to your hard avoids?{" "}
                    <button type="button" onClick={acceptPatternSuggestion}>
                      Yes, add it
                    </button>
                    <button type="button" onClick={() => setPatternResult(null)}>
                      No thanks
                    </button>
                  </div>
                </div>
              )}
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
              <button type="submit" style={{ alignSelf: "flex-start" }}>
                Save profile
              </button>
            </form>
            </section>
          </>
        )}

        {activeTab === "settings" && (
          <>
            <section className={styles.section}>
              <h2>Where to find each key</h2>
              <details>
                <summary style={{ cursor: "pointer", color: "#a5b4fc", fontSize: 14 }}>
                  Anthropic API key - click for steps
                </summary>
                <ol className={styles.subtitle} style={{ marginTop: 8 }}>
                  <li>Go to console.anthropic.com and sign in (or create an account)</li>
                  <li>Click "API Keys" in the left sidebar</li>
                  <li>Click "Create Key", give it any name</li>
                  <li>Copy the key (starts with sk-ant-...) and paste it below - it's only shown once</li>
                </ol>
              </details>
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer", color: "#a5b4fc", fontSize: 14 }}>
                  Slack webhook URL - click for steps
                </summary>
                <ol className={styles.subtitle} style={{ marginTop: 8 }}>
                  <li>Go to api.slack.com/apps and click "Create New App" (From scratch)</li>
                  <li>Name it anything, pick your workspace</li>
                  <li>Click "Incoming Webhooks" in the left menu, toggle it on</li>
                  <li>Click "Add New Webhook to Workspace", choose the channel you want alerts in</li>
                  <li>Copy the URL (starts with https://hooks.slack.com/...) and paste it below</li>
                </ol>
              </details>
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer", color: "#a5b4fc", fontSize: 14 }}>
                  JSearch API key - click for steps
                </summary>
                <ol className={styles.subtitle} style={{ marginTop: 8 }}>
                  <li>This one's currently shared and managed centrally - you don't need your own.</li>
                  <li>If that changes later, you'd sign up at the JSearch/OpenWebNinja site and grab a key the same way.</li>
                </ol>
              </details>
            </section>

            <section className={styles.section}>
              <h2>Your API keys</h2>
              <p className={styles.subtitle}>
                Anthropic key: <strong>{user.has_anthropic_key ? "set (yours)" : "not set - using shared key"}</strong>.
                Slack webhook: <strong>{user.has_slack_webhook ? "set" : "not set"}</strong>.
              </p>
              <form onSubmit={saveKeys} className={styles.form}>
                <label>
                  Anthropic API key
                  <input
                    type="password"
                    placeholder={user.has_anthropic_key ? "•••••••• (leave blank to keep)" : "sk-ant-... (optional - uses shared key if blank)"}
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
                <button type="submit" style={{ alignSelf: "flex-start" }}>
                  Save keys
                </button>
              </form>
            </section>

            <section className={styles.section}>
              <h2>Platform settings (PIN protected)</h2>
              <p className={styles.subtitle}>
                Shared Anthropic/JSearch keys, run schedule, and the JSearch quota cap. Changes here affect everyone.
              </p>

              {platformStatus && (
                <p className={styles.subtitle}>
                  Status: {platformStatus.paused ? "Paused" : "Active"} · Run times: {(platformStatus.run_times || []).join(", ")} ·
                  JSearch usage: {platformStatus.jsearch_calls_this_period}/{platformStatus.jsearch_quota_limit}
                </p>
              )}

              {!adminToken && platformStatus && !platformStatus.pin_set && (
                <div className={styles.form} style={{ maxWidth: 320 }}>
                  <label>
                    Set up a PIN (first time only)
                    <input type="password" value={newPinInput} onChange={(e) => setNewPinInput(e.target.value)} placeholder="At least 4 characters" />
                  </label>
                  <button type="button" onClick={submitNewPin} disabled={pinLoading}>
                    Set PIN
                  </button>
                  {pinError && <div className={styles.error}>{pinError}</div>}
                </div>
              )}

              {!adminToken && platformStatus && platformStatus.pin_set && (
                <div className={styles.form} style={{ maxWidth: 320 }}>
                  <label>
                    Enter PIN to unlock
                    <input type="password" value={pinInput} onChange={(e) => setPinInput(e.target.value)} />
                  </label>
                  <button type="button" onClick={submitPin} disabled={pinLoading}>
                    Unlock
                  </button>
                  {pinError && <div className={styles.error}>{pinError}</div>}
                </div>
              )}

              {adminToken && (
                <div className={styles.form}>
                  <label>
                    Shared Anthropic API key
                    <input
                      type="password"
                      placeholder={platformStatus?.has_anthropic_key ? "•••••••• (leave blank to keep)" : "sk-ant-..."}
                      value={platformForm.anthropic_api_key}
                      onChange={(e) => setPlatformForm({ ...platformForm, anthropic_api_key: e.target.value })}
                    />
                  </label>
                  <label>
                    Shared JSearch API key
                    <input
                      type="password"
                      placeholder={platformStatus?.has_jsearch_key ? "•••••••• (leave blank to keep)" : "uses GitHub secret if blank"}
                      value={platformForm.jsearch_api_key}
                      onChange={(e) => setPlatformForm({ ...platformForm, jsearch_api_key: e.target.value })}
                    />
                  </label>
                  <label>
                    Run times (UTC, comma-separated, e.g. 04:00, 09:00, 16:00)
                    <input
                      value={platformForm.run_times}
                      onChange={(e) => setPlatformForm({ ...platformForm, run_times: e.target.value })}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={platformForm.paused}
                      onChange={(e) => setPlatformForm({ ...platformForm, paused: e.target.checked })}
                      style={{ marginRight: 8 }}
                    />
                    Pause the pipeline (scheduled runs only - manual "Run now" still works)
                  </label>
                  <label>
                    JSearch monthly quota cap
                    <input
                      type="number"
                      value={platformForm.jsearch_quota_limit}
                      onChange={(e) => setPlatformForm({ ...platformForm, jsearch_quota_limit: e.target.value })}
                    />
                  </label>
                  <div>
                    <button type="button" onClick={savePlatformSettings}>
                      Save platform settings
                    </button>
                    <button type="button" onClick={lockPlatformSettings}>
                      Lock
                    </button>
                  </div>
                  {platformError && <div className={styles.error}>{platformError}</div>}
                </div>
              )}
            </section>

            {adminToken && (
              <section className={styles.section}>
                <h2>All users</h2>
                <p className={styles.subtitle}>
                  Every account on this platform, with their private dashboard link. Treat links like
                  passwords - anyone with one can edit that user's profile and keys.
                </p>
                {adminUsersError && <div className={styles.error}>{adminUsersError}</div>}
                {adminUserActionError && <div className={styles.error} style={{ marginTop: 8 }}>{adminUserActionError}</div>}
                <ul className={styles.list}>
                  {(adminUsers || []).map((u) => (
                    <li key={u.id} className={styles.listItem} style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
                        <span style={{ opacity: u.active ? 1 : 0.4 }}>
                          <strong>{u.name}</strong> {u.email ? `(${u.email})` : ""} {!u.active && "- inactive"}
                          <br />
                          <span className={styles.jobCompany}>
                            {u.phrase_count} phrases · {u.company_count} companies · {u.job_count} jobs found
                          </span>
                        </span>
                      </div>
                      <div>
                        {revealedLinkIds.includes(u.id) ? (
                          <code className={styles.linkBox} style={{ display: "block", marginBottom: 8 }}>
                            {`${typeof window !== "undefined" ? window.location.origin : ""}/dashboard/${u.access_token}`}
                          </code>
                        ) : null}
                        <button type="button" onClick={() => toggleLinkReveal(u.id)}>
                          {revealedLinkIds.includes(u.id) ? "Hide link" : "Show link"}
                        </button>
                        <button type="button" onClick={() => copyLink(u.access_token)}>
                          Copy link
                        </button>
                        <button type="button" onClick={() => runAdminUserAction(u.id, "toggle_active")}>
                          {u.active ? "Deactivate" : "Activate"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            runAdminUserAction(
                              u.id,
                              "regenerate_token",
                              `Regenerate ${u.name}'s link? Their old link will stop working immediately.`
                            )
                          }
                        >
                          Regenerate link
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            runAdminUserAction(
                              u.id,
                              "clear_data",
                              `Clear all job history for ${u.name}? This deletes their seen jobs and run logs, but keeps their profile, phrases, and companies.`
                            )
                          }
                        >
                          Clear job data
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            runAdminUserAction(
                              u.id,
                              "delete",
                              `Permanently delete ${u.name}'s account? This deletes everything - profile, phrases, companies, and job history. Cannot be undone.`
                            )
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </li>
                  ))}
                  {adminUsers && adminUsers.length === 0 && (
                    <p className={styles.subtitle}>No users yet.</p>
                  )}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
