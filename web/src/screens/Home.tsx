import { Icon, SourceNote } from "../components/UI";
import { count, headline, REPORT } from "../quality";
export default function Home() {
  const { results: r } = headline(REPORT);
  return (
    <div className="page home-page">
      <section className="home-hero">
        <div className="hero-copy rise">
          <div className="eyebrow">Know the rule. See the evidence.</div>
          <h1>
            Rules change.
            <br />
            Your research
            <br />
            <em>should keep up.</em>
          </h1>
          <p className="lead">
            Ask about Reserve Bank of India (RBI) lending rules. Explore cited
            passages and check which rules applied on the date that matters.
          </p>
          <div className="cta-row">
            <a className="primary" href="#ask">
              Try the research workspace <Icon name="arrow" />
            </a>
            <a className="text-link" href="#how">
              See how it works <Icon name="arrow" size={16} />
            </a>
          </div>
          <p className="hero-footnote">
            Built for lending compliance and credit-policy research.
            <br />
            New to the domain? Start with the saved example.
          </p>
        </div>
        <div
          className="hero-visual rise"
          aria-label="Illustration of the research process, not a live answer"
        >
          <div className="visual-caption">
            <span className="small-dot" /> From a question to its sources
            <span className="mono">THE IDEA</span>
          </div>
          <div className="visual-question">
            <Icon name="ask" />
            <span>
              Which rule applied
              <br />
              <strong>when this loan was made?</strong>
            </span>
          </div>
          <div className="visual-connector" aria-hidden="true" />
          <div className="visual-rule-row">
            <div className="visual-rule retired">
              <span className="mini-label">OLDER CIRCULAR</span>
              <span className="document-lines" />
              <span className="status-pill withdrawn">Withdrawn</span>
            </div>
            <span className="visual-arrow" aria-hidden="true">
              →
            </span>
            <div className="visual-rule current">
              <span className="mini-label">REPLACEMENT RULE</span>
              <span className="document-lines" />
              <span className="status-pill active">In force on date</span>
            </div>
          </div>
          <div className="visual-connector" aria-hidden="true" />
          <div className="visual-answer">
            <span className="answer-symbol">
              <Icon name="sources" />
            </span>
            <div>
              <strong>An answer you can inspect</strong>
              <span>Cited paragraph · research date · claim checks</span>
            </div>
          </div>
          <p className="visual-note">
            The original stays available for historical research.
          </p>
        </div>
      </section>
      <section className="context-band">
        <div className="eyebrow">The problem</div>
        <h2>An official source can still be an outdated source.</h2>
        <p>
          RBI withdraws old documents and publishes replacements at new
          addresses. A familiar link alone cannot tell a researcher which rule
          applied. This project connects source evidence, document history, and
          answers in one place.
        </p>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Evidence, with its limits</div>
            <h2>What the saved tests show</h2>
          </div>
          <a className="text-link" href="#evals">
            Inspect the results <Icon name="arrow" size={16} />
          </a>
        </div>
        <div className="metric-grid">
          <div className="metric-card featured">
            <span className="metric-label">Expected evidence cited</span>
            <strong>{count(r.gold_sentence_cited)}</strong>
            <p>
              Expected evidence sentences appeared in cited passages on the
              held-out test.
            </p>
            <SourceNote file="answers-test-gpt-4o-mini.json">
              n = 57 evidence sentences · 95% interval [0.807, 0.9649]
            </SourceNote>
          </div>
          <div className="metric-card">
            <span className="metric-label">Withdrawn evidence cited</span>
            <strong>{count(r.withdrawn_trap_cited_withdrawn)}</strong>
            <p>
              Withdrawn-rule trap questions cited a withdrawn document. Lower is
              better.
            </p>
            <SourceNote file="answers-test-gpt-4o-mini.json">
              n = 7 questions · 95% interval [0, 0]
            </SourceNote>
          </div>
          <div className="metric-card">
            <span className="metric-label">A limit worth knowing</span>
            <strong>6 of 21</strong>
            <p>
              Claims labelled not fully supported were caught by the model
              checker.
            </p>
            <SourceNote file="claim-checker-quality.json">
              n = 21 claims · model-drafted labels · no interval computed
            </SourceNote>
          </div>
        </div>
        <p className="fine-print">
          Evidence coverage is not answer accuracy. The tests are small and
          largely model-drafted; a citation or green check does not establish a
          correct interpretation.
        </p>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Choose your path</div>
            <h2>Try it. Inspect it. Understand it.</h2>
          </div>
        </div>
        <div className="journey-grid">
          {[
            [
              "ask",
              "Use the product",
              "Ask a question, choose a research date, and open the evidence behind an answer.",
              "Open workspace",
            ],
            [
              "graph",
              "Explore the connections",
              "Move through the rulebook in 3D. Follow documents, paragraphs, and replacement links.",
              "Explore the graph",
            ],
            [
              "built",
              "Read the engineering story",
              "See the trade-offs, measured improvements, and the limitations that shaped the product.",
              "Read build decisions",
            ],
          ].map(([route, title, text, action]) => (
            <a href={`#${route}`} className="journey-card" key={route}>
              <span className="card-icon">
                <Icon name={route} size={24} />
              </span>
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="card-action">
                {action}
                <Icon name="arrow" size={18} />
              </span>
            </a>
          ))}
        </div>
      </section>
      <section className="scope-strip">
        <Icon name="sources" size={24} />
        <div>
          <strong>A focused research corpus</strong>
          <p>
            Selected lending rules for non-banking financial companies (NBFCs),
            with older documents retained for history. This is an evaluated
            prototype, not a complete regulatory service.
          </p>
        </div>
        <a className="text-link" href="#sources">
          Browse the sources <Icon name="arrow" size={16} />
        </a>
      </section>
    </div>
  );
}
