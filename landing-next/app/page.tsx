const GITHUB = "https://github.com/truenorth-lj/open-intern";

export default function Home() {
  return (
    <>
      <div className="container">
        <nav>
          <a href="/" className="logo">open_intern</a>
          <div className="links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="#compare">Compare</a>
            <a href={GITHUB} target="_blank">GitHub</a>
          </div>
        </nav>
      </div>

      <div className="container">
        <section className="hero">
          <img src="/avatar.png" alt="Open Intern" width={80} height={80} style={{ borderRadius: "50%", marginBottom: 24 }} />
          <h1>An AI that actually<br />works here.</h1>
          <p>Open-source AI employee that joins your team as a real colleague — with its own identity, memory, and judgment.</p>
          <div className="cta">
            <a href="#get-started" className="btn btn-primary">Get Started</a>
            <a href={GITHUB} target="_blank" className="btn btn-secondary">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" /></svg>
              GitHub
            </a>
          </div>
        </section>
      </div>

      <div className="divider" />

      <div className="container">
        <section id="features">
          <p className="section-label">What it does</p>
          <h2>Your AI teammate, not another chatbot.</h2>
          <p className="section-desc">Open Intern lives in your team{"'"}s communication channels and works alongside you — with persistent memory and enterprise-grade safety.</p>
          <div className="features">
            <div className="feature"><h3>Multi-Platform</h3><p>Lives in Lark, Discord, Slack, or a web dashboard. Meets your team where they already work.</p></div>
            <div className="feature"><h3>Organizational Memory</h3><p>Three-layer memory (org, channel, personal) powered by pgvector. Remembers context like a real colleague.</p></div>
            <div className="feature"><h3>Multi-Agent Dashboard</h3><p>Manage all your AI agents from one unified interface. No more one-server-per-agent sprawl.</p></div>
            <div className="feature"><h3>Enterprise Safety</h3><p>Action classification, human approval workflows, and complete audit trails. Your policies, enforced.</p></div>
            <div className="feature"><h3>Elastic Scaling</h3><p>Scale to zero when idle, burst on demand. Sandboxed runtime means your data stays safe.</p></div>
            <div className="feature"><h3>Open Source</h3><p>MIT licensed. Self-hosted on your infrastructure. Zero telemetry. Full control, no lock-in.</p></div>
          </div>
        </section>
      </div>

      <div className="divider" />

      <div className="container">
        <section id="how-it-works">
          <p className="section-label">How it works</p>
          <h2>Up and running in minutes.</h2>
          <p className="section-desc">Three steps from clone to colleague.</p>
          <div className="steps">
            <div className="step">
              <div className="step-num">1</div>
              <div className="step-content"><h3>Deploy</h3><p>Clone the repo and run <code>docker compose up</code>. PostgreSQL, pgvector, and the agent start automatically.</p></div>
            </div>
            <div className="step">
              <div className="step-num">2</div>
              <div className="step-content"><h3>Configure</h3><p>Run <code>open_intern init</code> to choose your platform, enter credentials, and define your agent{"'"}s identity.</p></div>
            </div>
            <div className="step">
              <div className="step-num">3</div>
              <div className="step-content"><h3>Collaborate</h3><p>Your AI teammate joins the channel. Mention it, DM it, or let it proactively engage — it remembers everything.</p></div>
            </div>
          </div>
        </section>
      </div>

      <div className="divider" />

      <div className="container">
        <section id="compare">
          <p className="section-label">How it compares</p>
          <h2>Built different.</h2>
          <p className="section-desc">Open Intern is the enterprise AI teammate — not a personal assistant, not a CLI tool.</p>
          <table className="comparison-table">
            <thead><tr><th></th><th>Open Intern</th><th>OpenClaw</th><th>IronClaw</th></tr></thead>
            <tbody>
              <tr><td>Target</td><td>Teams &amp; enterprises</td><td>Individual users</td><td>Privacy-focused devs</td></tr>
              <tr><td>Memory</td><td>3-layer org memory</td><td>Per-user, flat</td><td>Single-user vector</td></tr>
              <tr><td>Multi-Agent</td><td>Unified dashboard</td><td>One per instance</td><td>One per instance</td></tr>
              <tr><td>Scaling</td><td>Elastic, scale to zero</td><td>One server each</td><td>One server each</td></tr>
              <tr><td>Isolation</td><td>Sandboxed runtime</td><td>Runs on host</td><td>WASM sandbox</td></tr>
              <tr><td>Telemetry</td><td>Zero</td><td>Opt-out</td><td>Zero</td></tr>
            </tbody>
          </table>
        </section>
      </div>

      <div className="divider" />

      <div className="container">
        <section id="get-started">
          <p className="section-label">Get started</p>
          <h2>Start in 30 seconds.</h2>
          <p className="section-desc">All you need is Docker.</p>
          <div className="code-block">
            <span className="comment"># Clone and start</span><br />
            git clone {GITHUB}.git<br />
            cd open_intern<br />
            docker compose up -d<br />
            <br />
            <span className="comment"># Initialize your agent</span><br />
            open_intern init<br />
            open_intern start
          </div>
        </section>
      </div>

      <div className="container">
        <footer>
          <p>open_intern — MIT License — <a href={GITHUB} target="_blank">GitHub</a></p>
        </footer>
      </div>
    </>
  );
}
