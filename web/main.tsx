import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./app/globals.css";
import Home from "./app/page";
import "./app/redesign.css";
import "./views/tv-presentation.css";
import "./components/shared/rail-status.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Slipstream root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <Home />
  </StrictMode>,
);
