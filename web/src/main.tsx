import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource/funnel-display/latin-500.css";
import "@fontsource/funnel-display/latin-600.css";
import "@fontsource/funnel-display/latin-700.css";
import "@fontsource/funnel-sans/latin-400.css";
import "@fontsource/funnel-sans/latin-500.css";
import "@fontsource/funnel-sans/latin-600.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
