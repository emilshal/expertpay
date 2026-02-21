import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DashboardPage from "./pages/DashboardPage";
import PayoutsPage from "./pages/PayoutsPage";
import SettingsPage from "./pages/SettingsPage";
import ConnectYandexPage from "./pages/ConnectYandexPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/payouts" element={<PayoutsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/connect-yandex" element={<ConnectYandexPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}

