import { PropsWithChildren, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { clearTokens, getActiveFleetName, getActiveRole, getIsPlatformAdmin } from "../lib/api";

const OWNER_MENU_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/deposits", label: "Deposits" },
  { to: "/payouts", label: "Payouts" },
  { to: "/fleet-members", label: "Team Access" }
];

const OPERATOR_MENU_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/payouts", label: "Payouts" }
];

const ADMIN_OWNER_MENU_ITEMS = [
  { to: "/deposit-review", label: "Deposit Review" },
  { to: "/driver-mappings", label: "Driver Mappings" },
  { to: "/settings", label: "Reconciliation" },
  { to: "/connect-yandex", label: "Yandex Overview" },
  { to: "/yandex-data", label: "Yandex Data" }
];

const PLATFORM_MENU_ITEMS = [
  { to: "/platform-earnings", label: "Platform Earnings" }
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
  const isPlatformAdmin = getIsPlatformAdmin();
  const isDriver = role === "driver";
  const isOperator = role === "operator";
  const isOwnerAdmin = role === "owner" || role === "admin";
  const menuItems = isDriver ? DRIVER_MENU_ITEMS : isOperator ? OPERATOR_MENU_ITEMS : isOwnerAdmin ? OWNER_MENU_ITEMS : [];

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
              {isDriver
                ? "Your payouts and bank details"
                : isOperator
                  ? "Operational sync and payout tools"
                  : isOwnerAdmin
                    ? "Fleet funding, payouts, and support tools"
                    : isPlatformAdmin
                      ? "Internal company reporting"
                      : "Navigation"}
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

        {isOwnerAdmin ? (
          <div className="sideMenuSection">
            <div className="sideMenuSectionLabel">Internal tools</div>
            <nav className="sideMenuNav" aria-label="Internal tools navigation">
              {ADMIN_OWNER_MENU_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `sideMenuLink sideMenuLinkSecondary ${isActive ? "sideMenuLinkActive" : ""}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        ) : null}

        {isPlatformAdmin ? (
          <div className="sideMenuSection">
            <div className="sideMenuSectionLabel">Platform</div>
            <nav className="sideMenuNav" aria-label="Platform navigation">
              {PLATFORM_MENU_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `sideMenuLink sideMenuLinkSecondary ${isActive ? "sideMenuLinkActive" : ""}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        ) : null}

        <button className="btn btnGhost sideMenuLogout" type="button" onClick={logout}>
          Log out
        </button>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
