import { createRoot } from "react-dom/client";
import App from "./App";

// Без StrictMode: @atlaskit/portal v6 теряет контент popup/drawer
// при двойном монтировании эффектов в dev-режиме.
createRoot(document.getElementById("root")!).render(<App />);
