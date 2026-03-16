import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DashboardPage from "./pages/DashboardPage";
import DepositsPage from "./pages/DepositsPage";
import PayoutsPage from "./pages/PayoutsPage";
import SettingsPage from "./pages/SettingsPage";
import ConnectYandexPage from "./pages/ConnectYandexPage";
import YandexOpsPage from "./pages/YandexOpsPage";
import FleetMembersPage from "./pages/FleetMembersPage";
import LoginPage from "./pages/LoginPage";
import { clearTokens, getAccessToken, me } from "./lib/api";

export default function App() {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthed, setAuthed] = useState(false);

  async function refreshSession() {
    const token = getAccessToken();
    if (!token) {
      setAuthed(false);
      setIsChecking(false);
      return;
    }

    try {
      await me();
      setAuthed(true);
    } catch {
      clearTokens();
      setAuthed(false);
    } finally {
      setIsChecking(false);
    }
  }

  useEffect(() => {
    void refreshSession();
  }, []);

  if (isChecking) {
    return (
      <div className="app">
        <main className="main">
          <section className="card">
            <p>Checking session...</p>
          </section>
        </main>
      </div>
    );
  }

  if (!isAuthed) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage onAuthenticated={refreshSession} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/deposits" element={<DepositsPage />} />
        <Route path="/payouts" element={<PayoutsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/fleet-members" element={<FleetMembersPage />} />
        <Route path="/connect-yandex" element={<ConnectYandexPage />} />
        <Route path="/yandex-ops" element={<YandexOpsPage />} />
        <Route path="/yandex-data" element={<YandexOpsPage />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}
