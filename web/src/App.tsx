import { lazy, Suspense, useEffect, useRef, useState } from "react";
import Home from "./screens/Home";
import Ask from "./screens/Ask";
import HowItWorks from "./screens/HowItWorks";
import HowIBuilt from "./screens/HowIBuilt";
import Quality from "./screens/Quality";
import HowWeTest from "./screens/HowWeTest";
import Sources from "./screens/Sources";
import { Icon } from "./components/UI";
import { REPO } from "./quality";
const KnowledgeGraph = lazy(() => import("./screens/KnowledgeGraph"));
const SCREENS = {
  home: "Overview",
  ask: "Ask a question",
  how: "How it works",
  built: "Build decisions",
  testing: "How we test",
  evals: "Results",
  sources: "Source library",
  graph: "Explore the graph",
} as const;
type Screen = keyof typeof SCREENS;
function current(): Screen {
  const route = window.location.hash.slice(1).split("/")[0];
  if (route === "research" || route === "try") return "ask";
  return Object.prototype.hasOwnProperty.call(SCREENS, route)
    ? (route as Screen)
    : "home";
}
export default function App() {
  const [screen, setScreen] = useState<Screen>(current);
  const [visited, setVisited] = useState<Set<Screen>>(
    () => new Set([current()]),
  );
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("theme") || "light";
    } catch {
      return "light";
    }
  });
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const change = () => {
      const next = current();
      setScreen(next);
      setVisited((previous) => new Set([...previous, next]));
      setMenu(false);
      window.scrollTo({ top: 0, behavior: "instant" });
      requestAnimationFrame(() => main.current?.focus({ preventScroll: true }));
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* usable without storage */
    }
  }, [theme]);
  useEffect(() => {
    document.title = `${SCREENS[screen]} · RBI Lending Intelligence`;
  }, [screen]);
  const navLink = (key: Screen) => (
    <a
      key={key}
      href={`#${key}`}
      aria-current={screen === key ? "page" : undefined}
      onClick={() => setMenu(false)}
    >
      <Icon name={key} />
      <span>{SCREENS[key]}</span>
      {key === "ask" && <span className="nav-dot" />}
    </a>
  );
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className={`sidebar ${menu ? "menu-open" : ""}`}>
        <a className="brand" href="#home">
          <span className="brand-mark">
            <Icon name="graph" size={25} />
          </span>
          <span>
            RBI Lending<span className="brand-sub">Intelligence</span>
          </span>
        </a>
        <button
          className="mobile-menu icon-button"
          aria-label={menu ? "Close navigation" : "Open navigation"}
          aria-expanded={menu}
          aria-controls="primary-nav"
          onClick={() => setMenu(!menu)}
        >
          <Icon name={menu ? "close" : "menu"} />
        </button>
        <nav
          id="primary-nav"
          className="primary-nav"
          aria-label="Main navigation"
        >
          <div className="nav-group">
            <span className="nav-label">The product</span>
            {(["home", "ask", "graph", "sources"] as Screen[]).map(navLink)}
          </div>
          <div className="nav-group">
            <span className="nav-label">Behind the product</span>
            {(["how", "built", "testing", "evals"] as Screen[]).map(navLink)}
          </div>
        </nav>
        <div className="sidebar-bottom">
          <p>
            An independent project
            <br />
            <strong>by Ashu</strong>
          </p>
          <a className="repo-link" href={REPO} target="_blank" rel="noreferrer">
            View source code <Icon name="external" size={15} />
          </a>
          <button
            className="theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Icon name="sun" size={16} />
            {theme === "dark" ? "Light appearance" : "Dark appearance"}
          </button>
        </div>
      </aside>
      <div className="workspace">
        <div className="topline">
          <span>
            <span className="small-dot" /> Evidence-led regulatory research
          </span>
          <span className="topline-right">Independent portfolio project</span>
        </div>
        <main id="main" tabIndex={-1} ref={main}>
          {visited.has("home") && (
            <div hidden={screen !== "home"}>
              <Home />
            </div>
          )}
          {visited.has("ask") && (
            <div hidden={screen !== "ask"}>
              <Ask active={screen === "ask"} />
            </div>
          )}
          {visited.has("how") && (
            <div hidden={screen !== "how"}>
              <HowItWorks active={screen === "how"} />
            </div>
          )}
          {visited.has("built") && (
            <div hidden={screen !== "built"}>
              <HowIBuilt />
            </div>
          )}
          {visited.has("testing") && (
            <div hidden={screen !== "testing"}>
              <HowWeTest />
            </div>
          )}
          {visited.has("evals") && (
            <div hidden={screen !== "evals"}>
              <Quality />
            </div>
          )}
          {visited.has("sources") && (
            <div hidden={screen !== "sources"}>
              <Sources />
            </div>
          )}
          {visited.has("graph") && (
            <div hidden={screen !== "graph"}>
              <Suspense
                fallback={
                  <div className="loading-state" role="status">
                    Opening the graph explorer…
                  </div>
                }
              >
                <KnowledgeGraph />
              </Suspense>
            </div>
          )}
        </main>
        <footer className="site-footer">
          <span>RBI Lending Intelligence</span>
          <span>
            Research support. Check the source before making a compliance
            decision.
          </span>
          <a href={REPO} target="_blank" rel="noreferrer">
            GitHub <Icon name="external" size={12} />
          </a>
        </footer>
      </div>
    </div>
  );
}
