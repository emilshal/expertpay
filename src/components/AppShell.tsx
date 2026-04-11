import { PropsWithChildren, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { clearTokens, getActiveFleetName, getActiveRole, getIsPlatformAdmin } from "../lib/api";
import LanguageToggle from "./LanguageToggle";
import { useI18n } from "../lib/i18n";

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
  const { pick } = useI18n();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const fleetName = getActiveFleetName();
  const role = getActiveRole();
  const isPlatformAdmin = getIsPlatformAdmin();
  const isDriver = role === "driver";
  const isOperator = role === "operator";
  const isOwnerAdmin = role === "owner" || role === "admin";
  const menuItems = isDriver ? DRIVER_MENU_ITEMS : isOperator ? OPERATOR_MENU_ITEMS : isOwnerAdmin ? OWNER_MENU_ITEMS : [];
  const translatedMenuItems = menuItems.map((item) => ({
    ...item,
    label:
      item.label === "Dashboard" ? pick("Dashboard", "დეშბორდი")
      : item.label === "Deposits" ? pick("Deposits", "შევსებები")
      : item.label === "Payouts" ? pick("Payouts", "გატანები")
      : item.label === "Team Access" ? pick("Team Access", "გუნდის წვდომა")
      : item.label === "My Wallet" ? pick("My Wallet", "ჩემი ბალანსი")
      : item.label
  }));
  const translatedAdminItems = ADMIN_OWNER_MENU_ITEMS.map((item) => ({
    ...item,
    label:
      item.label === "Deposit Review" ? pick("Deposit Review", "შევსებების განხილვა")
      : item.label === "Driver Mappings" ? pick("Driver Mappings", "მძღოლების მიბმა")
      : item.label === "Reconciliation" ? pick("Reconciliation", "შერიგება")
      : item.label === "Yandex Overview" ? pick("Yandex Overview", "Yandex მიმოხილვა")
      : item.label === "Yandex Data" ? pick("Yandex Data", "Yandex მონაცემები")
      : item.label
  }));
  const translatedPlatformItems = PLATFORM_MENU_ITEMS.map((item) => ({
    ...item,
    label: item.label === "Platform Earnings" ? pick("Platform Earnings", "პლატფორმის შემოსავალი") : item.label
  }));

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;

    const scrollY = window.scrollY;
    const html = document.documentElement;
    const body = document.body;
    const previousHtmlOverflow = html.style.overflow;
    const previousBodyOverflow = body.style.overflow;
    const previousBodyPosition = body.style.position;
    const previousBodyTop = body.style.top;
    const previousBodyLeft = body.style.left;
    const previousBodyRight = body.style.right;
    const previousBodyWidth = body.style.width;

    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";

    return () => {
      html.style.overflow = previousHtmlOverflow;
      body.style.overflow = previousBodyOverflow;
      body.style.position = previousBodyPosition;
      body.style.top = previousBodyTop;
      body.style.left = previousBodyLeft;
      body.style.right = previousBodyRight;
      body.style.width = previousBodyWidth;
      window.scrollTo(0, scrollY);
    };
  }, [menuOpen]);

  function logout() {
    clearTokens();
    window.location.assign("/login");
  }

  return (
    <div className="app">
      <header className="header">
        <NavLink className="brand" to="/dashboard" aria-label={pick("Go to dashboard", "გადადი დეშბორდზე")}>
          <div className="brandMark" aria-hidden="true">
            <span className="brandCurrency">₾</span>
          </div>
          <div>
            <div className="brandText">ExpertPay</div>
            {fleetName ? <div className="brandMeta">{fleetName}</div> : null}
          </div>
        </NavLink>

        <div className="headerActions">
          <LanguageToggle compact />
          <button
            className="menuToggle"
            type="button"
            aria-label={menuOpen ? pick("Close menu", "მენიუს დახურვა") : pick("Open menu", "მენიუს გახსნა")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </header>

      <div className={`menuOverlay ${menuOpen ? "menuOverlayOpen" : ""}`} onClick={() => setMenuOpen(false)} />

      <aside className={`sideMenu ${menuOpen ? "sideMenuOpen" : ""}`} aria-hidden={!menuOpen}>
        <div className="sideMenuHeader">
          <div>
            <div className="sideMenuTitle">{pick("Menu", "მენიუ")}</div>
            <div className="sideMenuSub">
              {isDriver
                ? pick("Your payouts and bank details", "თქვენი გატანები და ბანკის დეტალები")
                : isOperator
                  ? pick("Operational sync and payout tools", "ოპერაციული სინქი და გატანის ინსტრუმენტები")
                  : isOwnerAdmin
                    ? pick("Fleet funding, payouts, and support tools", "ფლიტის შევსება, გატანები და ოპერაციული ინსტრუმენტები")
                    : isPlatformAdmin
                      ? pick("Internal company reporting", "კომპანიის შიდა რეპორტინგი")
                      : pick("Navigation", "ნავიგაცია")}
            </div>
          </div>
          <button className="sideMenuClose" type="button" aria-label={pick("Close menu", "მენიუს დახურვა")} onClick={() => setMenuOpen(false)}>
            ×
          </button>
        </div>

        <nav className="sideMenuNav" aria-label={pick("Main navigation", "მთავარი ნავიგაცია")}>
          {translatedMenuItems.map((item) => (
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
            <div className="sideMenuSectionLabel">{pick("Internal tools", "შიდა ინსტრუმენტები")}</div>
            <nav className="sideMenuNav" aria-label={pick("Internal tools navigation", "შიდა ინსტრუმენტების ნავიგაცია")}>
              {translatedAdminItems.map((item) => (
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
            <div className="sideMenuSectionLabel">{pick("Platform", "პლატფორმა")}</div>
            <nav className="sideMenuNav" aria-label={pick("Platform navigation", "პლატფორმის ნავიგაცია")}>
              {translatedPlatformItems.map((item) => (
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
          {pick("Log out", "გასვლა")}
        </button>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
