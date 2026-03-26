import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DriverDashboardPage from "./pages/DriverDashboardPage";
import OperatorDashboardPage from "./pages/OperatorDashboardPage";
import OwnerDashboardPage from "./pages/OwnerDashboardPage";
import PlatformEarningsPage from "./pages/PlatformEarningsPage";
import CardTopupPage from "./pages/CardTopupPage";
import DepositsPage from "./pages/DepositsPage";
import DepositReviewPage from "./pages/DepositReviewPage";
import PayoutsPage from "./pages/PayoutsPage";
import SettingsPage from "./pages/SettingsPage";
import ConnectYandexPage from "./pages/ConnectYandexPage";
import YandexOpsPage from "./pages/YandexOpsPage";
import FleetMembersPage from "./pages/FleetMembersPage";
import DriverMappingsPage from "./pages/DriverMappingsPage";
import LoginPage from "./pages/LoginPage";
import { clearTokens, getAccessToken, getActiveRole, getIsPlatformAdmin, me } from "./lib/api";

export default function App() {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthed, setAuthed] = useState(false);
  const [role, setRole] = useState<"driver" | "operator" | "admin" | "owner" | null>(getActiveRole());
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(getIsPlatformAdmin());

  async function refreshSession() {
    const token = getAccessToken();
    if (!token) {
      setRole(null);
      setIsPlatformAdmin(false);
      setAuthed(false);
      setIsChecking(false);
      return;
    }

    try {
      const profile = await me();
      setRole(profile.role);
      setIsPlatformAdmin(Boolean(profile.is_platform_admin));
      setAuthed(true);
    } catch {
      clearTokens();
      setRole(null);
      setIsPlatformAdmin(false);
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
  const isOperator = role === "operator";
  const isOwnerAdmin = role === "owner" || role === "admin";
  const dashboardElement = isDriver
    ? <DriverDashboardPage />
    : isOperator
      ? <OperatorDashboardPage />
      : isOwnerAdmin
        ? <OwnerDashboardPage />
        : isPlatformAdmin
          ? <Navigate to="/platform-earnings" replace />
          : <Navigate to="/login" replace />;

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={dashboardElement} />
        <Route
          path="/platform-earnings"
          element={isPlatformAdmin ? <PlatformEarningsPage /> : <Navigate to="/dashboard" replace />}
        />
        <Route path="/card-topup" element={isOwnerAdmin ? <CardTopupPage /> : <Navigate to="/dashboard" replace />} />
        <Route path="/deposits" element={isOwnerAdmin ? <DepositsPage /> : <Navigate to="/dashboard" replace />} />
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
          path="/driver-mappings"
          element={isOwnerAdmin ? <DriverMappingsPage /> : <Navigate to="/dashboard" replace />}
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
