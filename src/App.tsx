import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DriverDashboardPage from "./pages/DriverDashboardPage";
import OwnerDashboardPage from "./pages/OwnerDashboardPage";
import CardTopupPage from "./pages/CardTopupPage";
import DepositsPage from "./pages/DepositsPage";
import DepositReviewPage from "./pages/DepositReviewPage";
import PayoutsPage from "./pages/PayoutsPage";
import SettingsPage from "./pages/SettingsPage";
import ConnectYandexPage from "./pages/ConnectYandexPage";
import YandexOpsPage from "./pages/YandexOpsPage";
import FleetMembersPage from "./pages/FleetMembersPage";
import LoginPage from "./pages/LoginPage";
import { clearTokens, getAccessToken, getActiveRole, me } from "./lib/api";

export default function App() {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthed, setAuthed] = useState(false);
  const [role, setRole] = useState<"driver" | "operator" | "admin" | "owner" | null>(getActiveRole());

  async function refreshSession() {
    const token = getAccessToken();
    if (!token) {
      setAuthed(false);
      setIsChecking(false);
      return;
    }

    try {
      const profile = await me();
      setRole(profile.role);
      setAuthed(true);
    } catch {
      clearTokens();
      setRole(null);
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

  const isDriver = role === "driver";
  const isOwnerAdmin = role === "owner" || role === "admin";

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={isDriver ? <DriverDashboardPage /> : <OwnerDashboardPage />} />
        <Route path="/card-topup" element={isDriver ? <Navigate to="/dashboard" replace /> : <CardTopupPage />} />
        <Route path="/deposits" element={isDriver ? <Navigate to="/dashboard" replace /> : <DepositsPage />} />
        <Route
          path="/deposit-review"
          element={isOwnerAdmin ? <DepositReviewPage /> : <Navigate to="/dashboard" replace />}
        />
        <Route path="/payouts" element={isDriver ? <Navigate to="/dashboard" replace /> : <PayoutsPage />} />
        <Route path="/settings" element={isOwnerAdmin ? <SettingsPage /> : <Navigate to="/dashboard" replace />} />
        <Route
          path="/fleet-members"
          element={isOwnerAdmin ? <FleetMembersPage /> : <Navigate to="/dashboard" replace />}
        />
        <Route
          path="/connect-yandex"
          element={isOwnerAdmin ? <ConnectYandexPage /> : <Navigate to="/dashboard" replace />}
        />
        <Route path="/yandex-ops" element={isOwnerAdmin ? <YandexOpsPage /> : <Navigate to="/dashboard" replace />} />
        <Route path="/yandex-data" element={isOwnerAdmin ? <YandexOpsPage /> : <Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}
