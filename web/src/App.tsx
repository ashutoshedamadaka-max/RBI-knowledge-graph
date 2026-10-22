import { useEffect, useState } from "react";
import Home from "./screens/Home";
import HowItWorks from "./screens/HowItWorks";
import HowIBuilt from "./screens/HowIBuilt";
import Quality from "./screens/Quality";
import Sources from "./screens/Sources";
import KnowledgeGraph from "./screens/KnowledgeGraph";

// Written for recruiters and hiring managers: each tab explains one side of the product on its own.
const SCREENS = {
  home: "Home", how: "How this works", built: "How I built this", evals: "Evals", sources: "Sources", graph: "Knowledge graph",
} as const;
type Screen = keyof typeof SCREENS;

function current(): Screen {
  const hash = window.location.hash.replace("#", "") as Screen;
  return hash in SCREENS ? hash : "home";
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(current);
  const [theme, setTheme] = useState<string>(() => {
    try { return localStorage.getItem("theme") ?? "auto"; } catch { return "auto"; }
  });

  useEffect(() => {
    const onHash = () => { setScreen(current()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* private mode: the choice lasts this visit */ }
  }, [theme]);
  useEffect(() => { document.title = screen === "home" ? "RBI Lending Intelligence" : `${SCREENS[screen]} · RBI Lending Intelligence`; }, [screen]);

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#home" style={{ color: "inherit", textDecoration: "none" }}>RBI Lending Intelligence<small>Answers from the RBI rules in force, with the evidence</small></a>
        <nav className="tabs" aria-label="Sections">
          {(Object.keys(SCREENS) as Screen[]).map((key) => (
            <button key={key} aria-current={screen === key ? "page" : undefined} onClick={() => { window.location.hash = key; }}>
              {SCREENS[key]}
            </button>
          ))}
        </nav>
        <button className="theme" onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "auto" : "dark")}
          aria-label={`Theme: ${theme}. Change theme`}>
          {theme === "auto" ? "Theme: system" : theme === "dark" ? "Theme: dark" : "Theme: light"}
        </button>
      </header>
      <main>
        {screen === "home" && <Home />}
        {screen === "how" && <HowItWorks />}
        {screen === "built" && <HowIBuilt />}
        {screen === "evals" && <Quality />}
        {screen === "sources" && <Sources />}
        {screen === "graph" && <KnowledgeGraph />}
      </main>
    </div>
  );
}
