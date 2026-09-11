import { createRoot } from "react-dom/client";
import App from "./App";
import { applyTheme, storedTheme } from "./theme";

// Без StrictMode: @atlaskit/portal v6 теряет контент popup/drawer
// при двойном монтировании эффектов в dev-режиме.
void applyTheme(storedTheme()).finally(() => {
  createRoot(document.getElementById("root")!).render(<App />);
});
