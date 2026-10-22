import { useEffect, useState } from "react";
import Ask from "./screens/Ask";
import RegulationMap from "./screens/RegulationMap";
import Quality from "./screens/Quality";
import Sources from "./screens/Sources";

const SCREENS = { ask: "Ask", map: "Regulation map", quality: "Quality", sources: "Sources and monitoring" } as const;
type Screen = keyof typeof SCREENS;

function current(): Screen {
  const hash = window.location.hash.replace("#", "") as Screen;
  return hash in SCREENS ? hash : "ask";
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(current);
  const [theme, setTheme] = useState<string>(() => {
    try { return localStorage.getItem("theme") ?? "auto"; } catch { return "auto"; }
  });

  useEffect(() => {
    const onHash = () => setScreen(current());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* private mode: the choice lasts this visit */ }
  }, [theme]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">RBI Lending Intelligence<small>NBFC lending rules, answered from the rules in force</small></div>
        <nav className="tabs" aria-label="Screens">
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
        {screen === "ask" && <Ask />}
        {screen === "map" && <RegulationMap />}
        {screen === "quality" && <Quality />}
        {screen === "sources" && <Sources />}
      </main>
    </div>
  );
}
