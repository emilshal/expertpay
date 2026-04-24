import { NavLink, Outlet } from "react-router-dom";
import LanguageToggle from "./LanguageToggle";
import { useI18n } from "../lib/i18n";

const PUBLIC_TABS = [
  { to: "/service", labelEn: "Service", labelKa: "სერვისი" },
  { to: "/about", labelEn: "About Us", labelKa: "ჩვენ შესახებ" },
  { to: "/contact", labelEn: "Contact", labelKa: "კონტაქტი" },
  { to: "/refund-policy", labelEn: "Refunds", labelKa: "დაბრუნება" },
  { to: "/privacy", labelEn: "Privacy", labelKa: "კონფიდენციალურობა" },
  { to: "/terms", labelEn: "Terms", labelKa: "წესები" },
  { to: "/login", labelEn: "Login", labelKa: "შესვლა" }
];

export default function PublicSiteLayout() {
  const { pick } = useI18n();

  return (
    <div className="publicPage">
      <header className="publicHeader">
        <div className="publicHeaderTop">
          <div className="brand">
            <div className="brandMark" aria-hidden="true">
              <span className="brandCurrency">₾</span>
            </div>
            <div>
              <div className="brandText">ExpertPay</div>
              <div className="brandMeta">{pick("Merchant Information", "მერჩანტის ინფორმაცია")}</div>
            </div>
          </div>
          <LanguageToggle compact />
        </div>

        <nav className="publicTabs" aria-label={pick("Public site navigation", "საჯარო ნავიგაცია")}>
          {PUBLIC_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) => `publicTab ${isActive ? "publicTabActive" : ""}`}
            >
              {pick(tab.labelEn, tab.labelKa)}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="publicMain">
        <Outlet />
      </main>
    </div>
  );
}
