import Ask from "./Ask";
import { count, headline, useQuality } from "../quality";

export default function Home() {
  const { report } = useQuality();
  const answers = report ? headline(report) : null;
  const r = answers?.results ?? {};
  const perQuestion = r.cost_usd?.per_question_answer_plus_rerank;

  return (
    <div className="page">
      <section className="hero rise">
        <div className="eyebrow">A compliance research tool for RBI lending rules</div>
        <h1>Ask a question about India's lending rules. Get an answer that cites the exact RBI paragraph, from the rule that was actually in force.</h1>
        <p className="lead">The Reserve Bank of India (RBI) regularly withdraws rules and replaces them with new ones. In November 2025 alone it withdrew 9,445 circulars (its official instructions to lenders) in a single notice. A compliance answer built on a withdrawn rule is a real business risk. This product tracks which rules are in force, answers only from those, and shows the evidence for every sentence it writes.</p>
        <div className="cta-row">
          <button className="primary" onClick={() => document.getElementById("try")?.scrollIntoView({ behavior: "smooth" })}>Try it with a real question</button>
          <a className="secondary" href="#how">See how it works</a>
          <a className="secondary" href="#built">How I built it</a>
        </div>
      </section>

      <section>
        <div className="grid-3">
          <div className="card kicker-card">
            <span className="pm-term">User</span>
            <h3>Who it is for</h3>
            <p>Compliance, credit-policy and risk teams at non-bank lenders (NBFCs) who need to know what RBI requires today, and what it required on a past date, with the source to prove it.</p>
          </div>
          <div className="card kicker-card">
            <span className="pm-term">Problem</span>
            <h3>What goes wrong today</h3>
            <p>RBI publishes a replacement at a new web address and stamps the old page "Withdrawn". Search tools and chatbots happily quote the old rule. Generic AI answers also invent details and rarely show where a claim came from.</p>
          </div>
          <div className="card kicker-card">
            <span className="pm-term">Value proposition</span>
            <h3>What this does differently</h3>
            <p>Every answer is built only from RBI paragraphs that were in force on the date asked, each sentence is checked against its cited text, and when the evidence is weak it declines to answer instead of guessing.</p>
          </div>
        </div>
      </section>

      <section>
        <div className="eyebrow">Measured, not claimed</div>
        <h2>Results on questions the system never saw while it was being tuned</h2>
        <div className="stat-strip">
          <div className="stat"><div className="big"><span className="num">{count(r.question_all_gold_cited)}</span></div><div className="label">answers cited the right RBI paragraph</div></div>
          <div className="stat"><div className="big"><span className="num">{count(r.withdrawn_trap_cited_withdrawn)}</span></div><div className="label">trick questions where a withdrawn rule was quoted (lower is better)</div></div>
          <div className="stat"><div className="big"><span className="num">{count(r.answerable_wrongly_refused)}</span></div><div className="label">answerable questions it wrongly refused</div></div>
          <div className="stat"><div className="big"><span className="num">{perQuestion ? `$${(perQuestion * 1000).toFixed(2)}` : "—"}</span></div><div className="label">cost per 1,000 questions</div></div>
        </div>
        <p className="muted">From the {answers?.split ?? "saved runs"}. The full method, confidence ranges and the failures are on the <a href="#evals">Evals</a> page. Scope: NBFC lending rules only, 88 RBI documents (16 rules in force plus the 72 older rules they replaced).</p>
      </section>

      <section id="try">
        <div className="eyebrow">Live product</div>
        <h2>Try it</h2>
        <p className="muted" style={{ maxWidth: 760 }}>Pick an example or type your own question. Watch the steps it takes, hover a sentence to see the RBI text behind it, and open the trace at the bottom to see exactly what happened, including time and cost.</p>
        <Ask />
      </section>

      <section>
        <h2>Explore</h2>
        <div className="grid-3">
          <a className="card kicker-card" href="#how" style={{ textDecoration: "none", color: "inherit" }}><h3>How this works →</h3><p>The end-to-end pipeline from question to checked answer, step by step.</p></a>
          <a className="card kicker-card" href="#built" style={{ textDecoration: "none", color: "inherit" }}><h3>How I built this →</h3><p>Problem framing, phased delivery, trade-offs, cost and what I learned.</p></a>
          <a className="card kicker-card" href="#evals" style={{ textDecoration: "none", color: "inherit" }}><h3>Evals →</h3><p>How quality is measured, the results, and where it still fails.</p></a>
          <a className="card kicker-card" href="#sources" style={{ textDecoration: "none", color: "inherit" }}><h3>Sources →</h3><p>What the product reads, how documents are cut, how rule status is tracked.</p></a>
          <a className="card kicker-card" href="#graph" style={{ textDecoration: "none", color: "inherit" }}><h3>Knowledge graph →</h3><p>The map of how rules connect, and what it is trusted for.</p></a>
        </div>
      </section>
    </div>
  );
}
