import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
// Fonts ship with the Studio: no request to a font CDN, and it works offline.
import "@fontsource-variable/geist/wght.css";
import "@fontsource-variable/geist-mono/wght.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
