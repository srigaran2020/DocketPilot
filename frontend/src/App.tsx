import { AnimatePresence } from "framer-motion";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/shell";
import { Dots } from "./components/ui";
import { useAuth } from "./lib/auth";
import Account from "./pages/Account";
import Ask from "./pages/Ask";
import CalendarPage from "./pages/Calendar";
import CaseDetail from "./pages/CaseDetail";
import Cases from "./pages/Cases";
import Dashboard from "./pages/Dashboard";
import Draft from "./pages/Draft";
import Guide from "./pages/Guide";
import Login from "./pages/Login";
import Research from "./pages/Research";
import Verify from "./pages/Verify";

function Private({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const { me } = useAuth();
  const loc = useLocation();
  if (!me) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <AppShell wide={wide}>{children}</AppShell>;
}

export default function App() {
  const { me, ready } = useAuth();
  if (!ready) return <div className="grid min-h-screen place-items-center"><Dots /></div>;
  return (
    <AnimatePresence mode="wait">
      <Routes>
        <Route path="/login" element={me ? <Navigate to="/dashboard" replace /> : <Login mode="signin" />} />
        <Route path="/signup" element={me ? <Navigate to="/dashboard" replace /> : <Login mode="signup" />} />
        <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
        <Route path="/ask" element={<Private wide><Ask /></Private>} />
        <Route path="/cases" element={<Private><Cases /></Private>} />
        <Route path="/cases/:id" element={<Private><CaseDetail /></Private>} />
        <Route path="/drafts/:id" element={<Private wide><Draft /></Private>} />
        <Route path="/calendar" element={<Private wide><CalendarPage /></Private>} />
        <Route path="/research" element={<Private><Research /></Private>} />
        <Route path="/verify" element={<Private><Verify /></Private>} />
        <Route path="/guide" element={<Private><Guide /></Private>} />
        <Route path="/account" element={<Private><Account /></Private>} />
        <Route path="*" element={<Navigate to={me ? "/dashboard" : "/login"} replace />} />
      </Routes>
    </AnimatePresence>
  );
}
