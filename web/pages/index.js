import { useState } from "react";
import styles from "../styles/shared.module.css";

export default function Home() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [link, setLink] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/create-user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to create account");
      setLink(`${window.location.origin}/dashboard/${data.access_token}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1>Job Monitor</h1>
        <p className={styles.subtitle}>
          Get a private dashboard that watches the job market for you and scores
          new postings against your profile, 3x a day.
        </p>

        {!link && (
          <form onSubmit={handleSubmit} className={styles.form}>
            <label>
              Your name
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label>
              Email (optional, just for your reference)
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            {error && <div className={styles.error}>{error}</div>}
            <button type="submit" disabled={loading}>
              {loading ? "Creating..." : "Create my dashboard"}
            </button>
          </form>
        )}

        {link && (
          <div className={styles.success}>
            <p>Your private dashboard link (save this - it's the only way to access your account):</p>
            <code className={styles.linkBox}>{link}</code>
            <a className={styles.cta} href={link}>
              Go to my dashboard →
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
