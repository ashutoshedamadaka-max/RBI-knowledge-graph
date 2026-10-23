import RegulationMap from "./RegulationMap";
import { NextPage, PageIntro, SourceNote } from "../components/UI";
import { REPORT } from "../quality";
export default function KnowledgeGraph() {
  const build = REPORT.graph_build.data;
  return (
    <div className="page graph-page">
      <PageIntro
        eyebrow="Knowledge graph"
        title="Explore how the rulebook connects."
      >
        Start with documents, then follow a relationship into the paragraphs
        behind it. A knowledge graph stores these connections explicitly, so
        they can be explored and used in search.
      </PageIntro>
      <RegulationMap />
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">What you are looking at</div>
            <h2>Connections with different jobs.</h2>
          </div>
        </div>
        <div className="grid-3">
          <div className="card">
            <h3>Source history</h3>
            <p className="muted">
              Replacement and withdrawal relationships connect old documents to
              the evidence that retired them. Suggested links keep their review
              status.
            </p>
          </div>
          <div className="card">
            <h3>Paragraph references</h3>
            <p className="muted">
              “See paragraph…” links can bring related evidence into the search.
              This is the graph behavior used in the answering path.
            </p>
          </div>
          <div className="card">
            <h3>Extracted meaning</h3>
            <p className="muted">
              Terms, entities, and obligations help explain the corpus.
              Machine-extracted “applies to” links are not trusted to filter
              answers.
            </p>
          </div>
        </div>
      </section>
      <section className="section-block">
        <div className="grid-2">
          <div className="card">
            <div className="eyebrow">Measured contribution</div>
            <h3>A useful link is more valuable than a larger graph.</h3>
            <p>
              On development questions requiring linked evidence, graph
              expansion found 24 of 26 expected spans in the top five, compared
              with 22 of 26 without it.
            </p>
            <SourceNote file="ladder-graph-dev.json">
              n = 26 evidence spans · no interval computed
            </SourceNote>
            <p className="fine-print" style={{ marginTop: 14 }}>
              This comparison did not include Cohere re-ranking. The question
              construction favors cross-references; incremental benefit on the
              final held-out answering path is not measured.
            </p>
          </div>
          <div className="card">
            <div className="eyebrow">Trust boundary</div>
            <h3>Extracted relationships can be wrong.</h3>
            <p>
              On the fresh reviewed sample, only 6 of 18 predicted “applies to”
              relationships were correct. Those links remain visible with a
              warning, and stay out of answer filtering.
            </p>
            <SourceNote file="graph-quality.json">
              n = 18 predicted links · model-drafted, reviewed labels · no
              interval computed
            </SourceNote>
          </div>
        </div>
      </section>
      <details className="disclosure">
        <summary>Inspect the full saved graph inventory</summary>
        <div>
          <p className="fine-print">
            These are counts from the saved graph build, not measures of answer
            quality. The withdrawal register is a document node in addition to
            the corpus documents.
          </p>
          <div className="grid-2">
            {[
              ["nodes", "Node type"],
              ["edges", "Relationship type"],
            ].map(([key, label]) => (
              <div className="table-wrap" key={key}>
                <table>
                  <thead>
                    <tr>
                      <th>{label}</th>
                      <th>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(build[key]).map(([type, n]) => (
                      <tr key={type}>
                        <td>{type.replaceAll("_", " ")}</td>
                        <td>{String(n)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <SourceNote file="graph-build.json">
            Complete saved graph inventory · no statistical interval
          </SourceNote>
        </div>
      </details>
      <NextPage
        href="#how"
        title="See where the graph fits in the pipeline."
        text="Follow a question through search, date filtering, ranking, and claim checks."
      />
    </div>
  );
}
