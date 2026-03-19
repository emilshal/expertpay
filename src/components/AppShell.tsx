import { PropsWithChildren, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { clearTokens, getActiveFleetName, getActiveRole } from "../lib/api";

const OWNER_MENU_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/deposits", label: "Deposits" },
  { to: "/card-topup", label: "Card Top-Up" },
  { to: "/payouts", label: "Payouts" }
];

const ADMIN_OWNER_MENU_ITEMS = [
  { to: "/deposit-review", label: "Deposit Review" },
  { to: "/fleet-members", label: "Team Access" },
  { to: "/driver-mappings", label: "Driver Mappings" },
  { to: "/settings", label: "Reconciliation" },
  { to: "/connect-yandex", label: "Yandex Ops" },
  { to: "/yandex-data", label: "Yandex Data" }
];

const DRIVER_MENU_ITEMS = [
  { to: "/dashboard", label: "My Wallet" }
];

export default function AppShell({ children }: PropsWithChildren) {
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const fleetName = getActiveFleetName();
  const role = getActiveRole();
  const isDriver = role === "driver";
  const isOwnerAdmin = role === "owner" || role === "admin";
  const menuItems = isDriver
    ? DRIVER_MENU_ITEMS
    : isOwnerAdmin
      ? [...OWNER_MENU_ITEMS, ...ADMIN_OWNER_MENU_ITEMS]
      : OWNER_MENU_ITEMS;

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  function logout() {
    clearTokens();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app">
      <header className="header">
        <NavLink className="brand" to="/dashboard" aria-label="Go to dashboard">
          <div className="brandMark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
              <path d="M12 6.2v11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              <path
                d="M15.8 7.6c0-1.7-1.7-3.1-3.8-3.1S8.2 5.9 8.2 7.6 9.8 10 12 10s3.8 1.2 3.8 3-1.7 3.1-3.8 3.1S8.2 14.7 8.2 13"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div>
            <div className="brandText">ExpertPay</div>
            {fleetName ? <div className="brandMeta">{fleetName}</div> : null}
          </div>
        </NavLink>

        <button
          className="menuToggle"
          type="button"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((value) => !value)}
        >
          <span />
          <span />
          <span />
        </button>
      </header>

      <div className={`menuOverlay ${menuOpen ? "menuOverlayOpen" : ""}`} onClick={() => setMenuOpen(false)} />

      <aside className={`sideMenu ${menuOpen ? "sideMenuOpen" : ""}`} aria-hidden={!menuOpen}>
        <div className="sideMenuHeader">
          <div>
            <div className="sideMenuTitle">Menu</div>
            <div className="sideMenuSub">
              {isDriver ? "Your payouts and bank details" : "Fleet funding, payouts, and support tools"}
            </div>
          </div>
          <button className="sideMenuClose" type="button" aria-label="Close menu" onClick={() => setMenuOpen(false)}>
            ×
          </button>
        </div>

        <nav className="sideMenuNav" aria-label="Main navigation">
          {menuItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `sideMenuLink ${isActive ? "sideMenuLinkActive" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <button className="btn btnGhost sideMenuLogout" type="button" onClick={logout}>
          Log out
        </button>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
