import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { Toaster } from "./components/toast";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <AuthProvider>
          <HashRouter>
            <App />
          </HashRouter>
          <Toaster />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
