import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  adminNetworkSummary,
  depositInstructions,
  depositsList,
  fleetMembers,
  getActiveFleetName,
  getActiveRole,
  ownerTransactionRows,
  type AdminNetworkSummary,
  ownerDriverFinanceRows,
  ownerFleetSummary,
  type DepositInstruction,
  type DepositItem,
  type FleetMember,
  type OwnerDriverFinanceRow,
  type OwnerFleetSummary,
  type OwnerTransactionRow
} from "../lib/api";
import InstallAppGuide from "../components/InstallAppGuide";
import { useI18n } from "../lib/i18n";

function formatApiError(error: unknown) {
  if (!(error instanceof Error)) return "Unable to load owner dashboard data.";
  const raw = error.message?.trim();
  if (!raw) return "Unable to load owner dashboard data.";

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

function formatMoney(value: string, currency: string) {
  return `${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(value || 0))} ${currency}`;
}

function formatDateTime(value: string, locale: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const normalizedLocale = locale === "ka-GE" ? "ka-GE" : "en-US";
  return new Intl.DateTimeFormat(normalizedLocale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function formatDateOnly(value: string, locale: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const normalizedLocale = locale === "ka-GE" ? "ka-GE" : "en-US";
  return new Intl.DateTimeFormat(normalizedLocale, {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}

function formatTimeOnly(value: string, locale: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const normalizedLocale = locale === "ka-GE" ? "ka-GE" : "en-US";
  return new Intl.DateTimeFormat(normalizedLocale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function MenuGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function TeamGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M16 19a4 4 0 0 0-8 0" />
      <circle cx="12" cy="9" r="3.25" />
      <path d="M21 18a3.25 3.25 0 0 0-3-3.22M6 14.78A3.25 3.25 0 0 0 3 18" />
    </svg>
  );
}

function WalletGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5z" />
      <path d="M4 9h16" />
      <circle cx="15.5" cy="14" r="1.25" />
    </svg>
  );
}

function LoopGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7.5 8.5A5.5 5.5 0 0 1 17 10h2.5" />
      <path d="M16.5 5.5 19.5 10l-4.5 3" />
      <path d="M16.5 15.5A5.5 5.5 0 0 1 7 14H4.5" />
      <path d="M7.5 18.5 4.5 14l4.5-3" />
    </svg>
  );
}

function StarGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <path d="m12 3.8 2.5 5.07 5.6.82-4.05 3.95.96 5.56L12 16.55 7 19.2l.99-5.56L3.95 9.7l5.57-.82z" />
    </svg>
  );
}

function SliderGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 6h7M14 6h6M4 12h12M19 12h1M4 18h3M10 18h10" />
      <circle cx="11" cy="6" r="2" />
      <circle cx="17" cy="12" r="2" />
      <circle cx="8" cy="18" r="2" />
    </svg>
  );
}

function SearchGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-4.2-4.2" />
    </svg>
  );
}

function RefreshGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M20 11a8 8 0 1 0 2.1 5.4" />
      <path d="M20 4v7h-7" />
    </svg>
  );
}

function CopyGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function SettingsGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 8.5A3.5 3.5 0 1 0 12 15.5 3.5 3.5 0 0 0 12 8.5z" />
      <path d="M19.4 15a1 1 0 0 0 .2 1.1l.04.04a1.8 1.8 0 0 1 0 2.55 1.8 1.8 0 0 1-2.55 0l-.04-.04a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.91V19.5A1.8 1.8 0 0 1 13.6 21h-3.2A1.8 1.8 0 0 1 8.6 19.5v-.08a1 1 0 0 0-.6-.91 1 1 0 0 0-1.1.2l-.04.04a1.8 1.8 0 0 1-2.55 0 1.8 1.8 0 0 1 0-2.55l.04-.04a1 1 0 0 0 .2-1.1 1 1 0 0 0-.91-.6H3.5A1.8 1.8 0 0 1 2 12.6v-1.2A1.8 1.8 0 0 1 3.5 9.6h.08a1 1 0 0 0 .91-.6 1 1 0 0 0-.2-1.1l-.04-.04a1.8 1.8 0 0 1 0-2.55 1.8 1.8 0 0 1 2.55 0l.04.04a1 1 0 0 0 1.1.2 1 1 0 0 0 .6-.91V4.5A1.8 1.8 0 0 1 10.4 3h3.2A1.8 1.8 0 0 1 15.4 4.5v.08a1 1 0 0 0 .6.91 1 1 0 0 0 1.1-.2l.04-.04a1.8 1.8 0 0 1 2.55 0 1.8 1.8 0 0 1 0 2.55l-.04.04a1 1 0 0 0-.2 1.1 1 1 0 0 0 .91.6h.08A1.8 1.8 0 0 1 22 11.4v1.2a1.8 1.8 0 0 1-1.5 1.8h-.08a1 1 0 0 0-.91.6z" />
    </svg>
  );
}

function buildAlerts(summary: OwnerFleetSummary | null, currency: string, pick: (english: string, georgian: string) => string) {
  if (!summary) return [];
  const reserve = Number(summary.reserve_balance || 0);
  const pendingTotal = Number(summary.pending_payouts_total || 0);
  const alerts: Array<{ key: string; tone: "danger" | "warn" | "info"; title: string; detail: string; cta: string; to: string }> = [];

  if (reserve <= 0) {
    alerts.push({
      key: "reserve-empty",
      tone: "danger",
      title: pick("Fleet reserve is empty", "ფლიტის რეზერვი ცარიელია"),
      detail: pick("Drivers will not be able to withdraw until you add funds to the fleet reserve.", "მძღოლები ვერ გაიტანენ თანხას, სანამ ფლიტის რეზერვს არ შეავსებთ."),
      cta: pick("Fund fleet", "ფლიტის შევსება"),
      to: "/deposits"
    });
  } else if (summary.pending_payouts_count > 0 && reserve <= pendingTotal) {
    alerts.push({
      key: "reserve-low",
      tone: "warn",
      title: pick("Fleet reserve is running low", "ფლიტის რეზერვი იწურება"),
      detail: pick(
        `Pending payouts total ${formatMoney(summary.pending_payouts_total, currency)}, which is at or above the current reserve.`,
        `მოლოდინში მყოფი გატანების ჯამია ${formatMoney(summary.pending_payouts_total, currency)}, რაც მიმდინარე რეზერვს უტოლდება ან აჭარბებს.`
      ),
      cta: pick("Add funds", "თანხის დამატება"),
      to: "/deposits"
    });
  }

  if (summary.unmatched_deposits_count > 0) {
    alerts.push({
      key: "deposit-review",
      tone: "warn",
      title: pick("Incoming deposits need review", "შემოსული შევსებები განხილვას საჭიროებს"),
      detail: pick(
        `${summary.unmatched_deposits_count} bank transfer${summary.unmatched_deposits_count === 1 ? "" : "s"} are waiting to be matched to this fleet.`,
        `${summary.unmatched_deposits_count} საბანკო გადარიცხვა ელოდება ამ ფლიტზე მიბმას.`
      ),
      cta: pick("Review deposits", "შევსებების განხილვა"),
      to: "/deposit-review"
    });
  }

  if (summary.failed_payouts_count > 0) {
    alerts.push({
      key: "failed-payouts",
      tone: "danger",
      title: pick("Some payouts need attention", "ზოგიერთ გატანას ყურადღება სჭირდება"),
      detail: pick(
        `${summary.failed_payouts_count} payout${summary.failed_payouts_count === 1 ? "" : "s"} failed for ${formatMoney(summary.failed_payouts_total, currency)}.`,
        `${summary.failed_payouts_count} გატანა ჩავარდა ${formatMoney(summary.failed_payouts_total, currency)} ოდენობაზე.`
      ),
      cta: pick("Open payouts", "გატანების გახსნა"),
      to: "/payouts"
    });
  }

  if (summary.pending_payouts_count >= 3) {
    alerts.push({
      key: "pending-payouts",
      tone: "info",
      title: pick("Payouts are building up", "გატანები გროვდება"),
      detail: pick(
        `${summary.pending_payouts_count} payouts are still waiting to finish.`,
        `${summary.pending_payouts_count} გატანა ჯერ კიდევ დასრულებას ელოდება.`
      ),
      cta: pick("Check status", "სტატუსის შემოწმება"),
      to: "/payouts"
    });
  }

  return alerts;
}

export default function OwnerDashboardPage() {
  const { pick, locale } = useI18n();
  const role = getActiveRole();
  const isOwner = role === "owner";
  const isOwnerAdmin = role === "owner" || role === "admin";
  const today = useMemo(() => new Date(), []);
  const [summary, setSummary] = useState<OwnerFleetSummary | null>(null);
  const [adminSummary, setAdminSummary] = useState<AdminNetworkSummary | null>(null);
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [deposits, setDeposits] = useState<DepositItem[]>([]);
  const [members, setMembers] = useState<FleetMember[]>([]);
  const [driverFinanceRows, setDriverFinanceRows] = useState<OwnerDriverFinanceRow[]>([]);
  const [ownerTransactions, setOwnerTransactions] = useState<OwnerTransactionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | FleetMember["role"]>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [fromDate, setFromDate] = useState(toDateInputValue(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 30)));
  const [toDate, setToDate] = useState(toDateInputValue(today));
  const [financeSearch, setFinanceSearch] = useState("");
  const [financeFromDate, setFinanceFromDate] = useState(toDateInputValue(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 30)));
  const [financeToDate, setFinanceToDate] = useState(toDateInputValue(today));
  const [copiedLink, setCopiedLink] = useState(false);
  const [ownerRailOpen, setOwnerRailOpen] = useState(true);
  const [ownerSection, setOwnerSection] = useState<"roster" | "transactions" | "wallet">("roster");
  const [showWithdrawnBreakdown, setShowWithdrawnBreakdown] = useState(false);
  const [openPendingFleetId, setOpenPendingFleetId] = useState<number | null>(null);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [summaryData, instructionData, depositData, financeData, transactionData, adminSummaryData] = await Promise.all([
        ownerFleetSummary(),
        depositInstructions(),
        depositsList(),
        ownerDriverFinanceRows(),
        ownerTransactionRows(),
        isOwner ? Promise.resolve(null) : adminNetworkSummary()
      ]);
      const fleetName = summaryData.fleet_name || instructionData.fleet_name || getActiveFleetName() || "";
      const memberData = fleetName ? await fleetMembers(fleetName) : [];
      setSummary(summaryData);
      setAdminSummary(adminSummaryData);
      setInstructions(instructionData);
      setDeposits(depositData.slice(0, 3));
      setMembers(memberData);
      setDriverFinanceRows(financeData);
      setOwnerTransactions(transactionData);
      setOpenPendingFleetId((current) =>
        adminSummaryData?.pending_by_fleet.some((item) => item.fleet_id === current) ? current : null
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : pick("Unable to load owner dashboard data.", "მფლობელის დეშბორდის მონაცემები ვერ ჩაიტვირთა."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const currency = summary?.currency ?? instructions?.currency ?? "GEL";
  const alerts = buildAlerts(summary, currency, pick);
  const activeFleetName = summary?.fleet_name ?? instructions?.fleet_name ?? getActiveFleetName() ?? "";
  const adminCurrency = adminSummary?.currency ?? currency;
  const inviteLink = useMemo(() => {
    if (!activeFleetName || typeof window === "undefined") return "";
    return `${window.location.origin}/login?fleet=${encodeURIComponent(activeFleetName)}`;
  }, [activeFleetName]);

  const filteredMembers = useMemo(() => {
    const query = memberSearch.trim().toLowerCase();
    const from = fromDate ? new Date(`${fromDate}T00:00:00`) : null;
    const to = toDate ? new Date(`${toDate}T23:59:59`) : null;

    return members.filter((member) => {
      const createdAt = member.created_at ? new Date(member.created_at) : null;
      if (from && createdAt && createdAt < from) return false;
      if (to && createdAt && createdAt > to) return false;
      if (roleFilter !== "all" && member.role !== roleFilter) return false;
      if (statusFilter === "active" && !member.is_active) return false;
      if (statusFilter === "inactive" && member.is_active) return false;
      if (!query) return true;
      const haystack = [
        String(member.id),
        member.first_name,
        member.last_name,
        member.username,
        member.phone_number
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [fromDate, memberSearch, members, roleFilter, statusFilter, toDate]);

  const filteredFinanceRows = useMemo(() => {
    const query = financeSearch.trim().toLowerCase();
    const from = financeFromDate ? new Date(`${financeFromDate}T00:00:00`) : null;
    const to = financeToDate ? new Date(`${financeToDate}T23:59:59`) : null;

    return driverFinanceRows.filter((row) => {
      const createdAt = row.created_at ? new Date(row.created_at) : null;
      if (from && createdAt && createdAt < from) return false;
      if (to && createdAt && createdAt > to) return false;
      if (!query) return true;
      const haystack = [
        String(row.id),
        row.first_name,
        row.last_name,
        row.phone_number
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [driverFinanceRows, financeFromDate, financeSearch, financeToDate]);

  async function handleCopyFleetLink() {
    if (!inviteLink || typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(inviteLink);
    setCopiedLink(true);
    window.setTimeout(() => setCopiedLink(false), 1800);
  }

  if (isOwner) {
    return (
      <div className="ownerDashboard ownerExecutiveDashboard">
        <section className={`ownerRosterShell ${ownerRailOpen ? "" : "ownerRosterShellCollapsed"}`}>
          <aside className={`ownerRosterRail ${ownerRailOpen ? "" : "ownerRosterRailCollapsed"}`}>
            <div className="ownerRosterLogo">₾</div>
            <nav className="ownerRosterRailNav" aria-label={pick("Owner sections", "მფლობელის სექციები")}>
              <button
                className={`ownerRosterRailLink ${ownerSection === "roster" ? "ownerRosterRailLinkActive" : ""}`}
                type="button"
                aria-label={pick("Driver list", "მძღოლების სია")}
                onClick={() => setOwnerSection("roster")}
              >
                <TeamGlyph />
              </button>
              <button
                className={`ownerRosterRailLink ${ownerSection === "transactions" ? "ownerRosterRailLinkActive" : ""}`}
                type="button"
                aria-label={pick("Fleet transactions", "ფლიტის ტრანზაქციები")}
                onClick={() => setOwnerSection("transactions")}
              >
                <LoopGlyph />
              </button>
              <button
                className={`ownerRosterRailLink ${ownerSection === "wallet" ? "ownerRosterRailLinkActive" : ""}`}
                type="button"
                aria-label={pick("Driver balances", "მძღოლების ბალანსები")}
                onClick={() => setOwnerSection("wallet")}
              >
                <WalletGlyph />
              </button>
              <Link className="ownerRosterRailLink" to="/payouts" aria-label={pick("Payouts", "გატანები")}>
                <StarGlyph />
              </Link>
              <Link className="ownerRosterRailLink" to="/settings" aria-label={pick("Tools", "ინსტრუმენტები")}>
                <SliderGlyph />
              </Link>
            </nav>
          </aside>

          <div className="ownerRosterMain">
            <div className="ownerRosterTopline">
              <button
                className="ownerRosterUtilityButton"
                type="button"
                aria-label={pick("Owner menu", "მფლობელის მენიუ")}
                aria-expanded={ownerRailOpen}
                onClick={() => setOwnerRailOpen((current) => !current)}
              >
                <MenuGlyph />
              </button>
              <div className="ownerRosterMetricChip">
                <StarGlyph />
                <span>{pick("Owner", "მფლობელი")}</span>
              </div>
              <div className="ownerRosterReserveChip">
                <span className="ownerRosterReserveIcon">₾</span>
                <span>{formatMoney(summary?.reserve_balance ?? "0.00", currency)}</span>
              </div>
              <Link className="ownerRosterUtilityButton" to="/settings" aria-label={pick("Open settings", "პარამეტრების გახსნა")}>
                <SettingsGlyph />
              </Link>
            </div>

            <div className="ownerRosterIntro">
              <div className="ownerRosterSubtitle">{activeFleetName || pick("Active fleet", "აქტიური ფლიტი")}</div>
              <div className="ownerRosterTitleRow">
                <h1 className="ownerRosterTitle">
                  {ownerSection === "wallet"
                    ? pick("Driver balances", "მძღოლების ბალანსები")
                    : ownerSection === "transactions"
                      ? pick("Fleet transactions", "ფლიტის ტრანზაქციები")
                      : pick("Driver roster", "მძღოლების სია")}
                </h1>
                <InstallAppGuide />
              </div>
            </div>

            {error ? <p className="statusError">{formatApiError(error)}</p> : null}

            {ownerSection === "wallet" ? (
              <>
                <div className="ownerRosterControls ownerFinanceControls">
                  <div className="ownerRosterDateRow">
                    <label className="ownerRosterField">
                      <input
                        className="ownerRosterInput"
                        type="date"
                        value={financeFromDate}
                        onChange={(event) => setFinanceFromDate(event.target.value)}
                      />
                    </label>
                    <label className="ownerRosterField">
                      <input
                        className="ownerRosterInput"
                        type="date"
                        value={financeToDate}
                        onChange={(event) => setFinanceToDate(event.target.value)}
                      />
                    </label>
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh balances", "ბალანსების განახლება")}>
                      <RefreshGlyph />
                    </button>
                  </div>

                  <div className="ownerRosterSearchRow">
                    <label className="ownerRosterField ownerRosterFieldGrow">
                      <input
                        className="ownerRosterInput"
                        type="text"
                        placeholder={pick("Search by id, name, or phone", "ძებნა ID-ით, სახელით ან ნომრით")}
                        value={financeSearch}
                        onChange={(event) => setFinanceSearch(event.target.value)}
                      />
                    </label>
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh finance table", "ფინანსური ცხრილის განახლება")}>
                      <SearchGlyph />
                    </button>
                  </div>
                </div>

                <div className="ownerRosterSummaryRow">
                  <div className="ownerRosterSummaryChip">
                    <span className="ownerRosterSummaryLabel">{pick("Visible balance", "ნაჩვენები ბალანსი")}</span>
                    <span className="ownerRosterSummaryValue">
                      {formatMoney(
                        String(
                          filteredFinanceRows.reduce(
                            (total, row) => total + Number(row.available_balance || 0),
                            0
                          )
                        ),
                        currency
                      )}
                    </span>
                  </div>
                </div>

                <div className="ownerFinanceTableWrap">
                  <table className="ownerFinanceTable">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>{pick("First name", "სახელი")}</th>
                        <th>{pick("Last name", "გვარი")}</th>
                        <th>{pick("Transactions", "ტრანზაქციები")}</th>
                        <th>{pick("Balance", "ბალანსი")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredFinanceRows.length ? (
                        filteredFinanceRows.map((row) => (
                          <tr key={row.id}>
                            <td>{row.id}</td>
                            <td>
                              <div>{row.first_name || "—"}</div>
                              <div className="ownerRosterMemberMeta">{row.phone_number}</div>
                            </td>
                            <td>{row.last_name || "—"}</td>
                            <td>{row.transaction_count}</td>
                            <td>{formatMoney(row.available_balance, row.currency)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="ownerFinanceEmptyCell" colSpan={5}>
                            {pick("No drivers match these filters right now.", "ამ ფილტრებით მძღოლები ახლა ვერ მოიძებნა.")}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : ownerSection === "transactions" ? (
              <>
                <div className="ownerRosterControls ownerFinanceControls">
                  <div className="ownerRosterDateRow">
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh transactions", "ტრანზაქციების განახლება")}>
                      <RefreshGlyph />
                    </button>
                  </div>
                </div>

                <div className="ownerFinanceTableWrap">
                  <table className="ownerFinanceTable">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>{pick("Transaction type", "ტრანზაქციის ტიპი")}</th>
                        <th>{pick("Amount", "თანხა")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ownerTransactions.length ? (
                        ownerTransactions.map((row) => (
                          <tr key={row.id}>
                            <td>{row.id}</td>
                            <td>{pick(row.transaction_type, row.transaction_type === "Deposit" ? "შევსება" : "გატანა")}</td>
                            <td>{formatMoney(row.amount, row.currency)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="ownerFinanceEmptyCell" colSpan={3}>
                            {pick("No transactions yet for this fleet.", "ამ ფლიტისთვის ტრანზაქციები ჯერ არ არის.")}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <>
                <div className="ownerRosterControls">
                  <div className="ownerRosterDateRow">
                    <label className="ownerRosterField">
                      <input
                        className="ownerRosterInput"
                        type="date"
                        value={fromDate}
                        onChange={(event) => setFromDate(event.target.value)}
                      />
                    </label>
                    <label className="ownerRosterField">
                      <input
                        className="ownerRosterInput"
                        type="date"
                        value={toDate}
                        onChange={(event) => setToDate(event.target.value)}
                      />
                    </label>
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh owner panel", "მფლობელის პანელის განახლება")}>
                      <RefreshGlyph />
                    </button>
                  </div>

                  <div className="ownerRosterSearchRow">
                    <label className="ownerRosterField ownerRosterFieldGrow">
                      <input
                        className="ownerRosterInput"
                        type="text"
                        placeholder={pick("Search by id, name, or phone", "ძებნა ID-ით, სახელით ან ნომრით")}
                        value={memberSearch}
                        onChange={(event) => setMemberSearch(event.target.value)}
                      />
                    </label>
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh members", "მძღოლების განახლება")}>
                      <SearchGlyph />
                    </button>
                  </div>

                  <div className="ownerRosterLinkRow">
                    <div className="ownerRosterLinkField">
                      <input className="ownerRosterInput ownerRosterInputLink" type="text" readOnly value={inviteLink} />
                      <button className="ownerRosterCopyButton" type="button" onClick={() => void handleCopyFleetLink()} aria-label={pick("Copy fleet link", "ფლიტის ლინკის დაკოპირება")}>
                        <CopyGlyph />
                      </button>
                    </div>
                    {copiedLink ? <div className="ownerRosterCopied">{pick("Copied", "დაკოპირდა")}</div> : null}
                  </div>

                  <div className="ownerRosterSelectRow">
                    <label className="ownerRosterField ownerRosterFieldGrow">
                      <select
                        className="ownerRosterSelect"
                        value={roleFilter}
                        onChange={(event) => setRoleFilter(event.target.value as "all" | FleetMember["role"])}
                      >
                        <option value="all">{pick("All roles", "ყველა როლი")}</option>
                        <option value="driver">{pick("Driver", "მძღოლი")}</option>
                        <option value="operator">{pick("Operator", "ოპერატორი")}</option>
                        <option value="admin">{pick("Admin", "ადმინისტრატორი")}</option>
                        <option value="owner">{pick("Owner", "მფლობელი")}</option>
                      </select>
                    </label>
                    <label className="ownerRosterField ownerRosterFieldGrow">
                      <select
                        className="ownerRosterSelect"
                        value={statusFilter}
                        onChange={(event) => setStatusFilter(event.target.value as "all" | "active" | "inactive")}
                      >
                        <option value="all">{pick("All statuses", "ყველა სტატუსი")}</option>
                        <option value="active">{pick("Active", "აქტიური")}</option>
                        <option value="inactive">{pick("Inactive", "არააქტიური")}</option>
                      </select>
                    </label>
                  </div>
                </div>

                <div className="ownerRosterTable" role="table" aria-label={pick("Fleet members", "ფლიტის წევრები")}>
                  <div className="ownerRosterTableHeader" role="row">
                    <div className="ownerRosterCell ownerRosterCellId" role="columnheader">ID</div>
                    <div className="ownerRosterCell" role="columnheader">{pick("First name", "სახელი")}</div>
                    <div className="ownerRosterCell" role="columnheader">{pick("Last name", "გვარი")}</div>
                  </div>

                  {filteredMembers.length ? (
                    filteredMembers.map((member) => (
                      <div key={member.id} className="ownerRosterTableRow" role="row">
                        <div className="ownerRosterCell ownerRosterCellId" role="cell">{member.id}</div>
                        <div className="ownerRosterCell" role="cell">
                          <div>{member.first_name || member.username}</div>
                          <div className="ownerRosterMemberMeta">{member.phone_number}</div>
                        </div>
                        <div className="ownerRosterCell" role="cell">
                          <div>{member.last_name || "—"}</div>
                          <div className="ownerRosterMemberMeta">
                            {pick(member.role, member.role === "driver" ? "მძღოლი" : member.role === "operator" ? "ოპერატორი" : member.role === "admin" ? "ადმინისტრატორი" : "მფლობელი")}
                            {" · "}
                            {member.is_active ? pick("active", "აქტიური") : pick("inactive", "არააქტიური")}
                            {" · "}
                            {formatDateOnly(member.created_at, locale)}
                            {" · "}
                            {formatTimeOnly(member.created_at, locale)}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="ownerRosterEmpty">
                      <div className="ownerRosterEmptyTitle">{pick("No members match these filters", "ამ ფილტრებით წევრები ვერ მოიძებნა")}</div>
                      <div className="ownerRosterEmptyText">{pick("Try widening the date range or clearing the search to see more drivers and operators.", "იხილეთ მეტი მძღოლი და ოპერატორი თარიღების გაფართოებით ან ძიების გაწმენდით.")}</div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="ownerDashboard">
      <section className="card ownerHero">
        <div className="ownerHeroTop">
          <div className="ownerHeroEyebrow">{pick("Total funded", "ჯამურად შევსებულია")}</div>
          <InstallAppGuide />
        </div>
        <div className="ownerHeroBalance">
          {formatMoney(adminSummary?.total_funded ?? "0.00", adminCurrency)}
        </div>
        <p className="ownerHeroNote">
          {pick(
            "This is the total amount funded into ExpertPay across all fleets. The tools below still work on your currently selected fleet.",
            "ეს არის ExpertPay-ში ყველა ფლიტის მიერ ჯამურად შეტანილი თანხა. ქვემოთ არსებული ინსტრუმენტები მაინც თქვენს ამჟამად არჩეულ ფლიტზე მუშაობს."
          )}
        </p>
        <div className="ownerHeroMeta">
          {loading ? (
            <span>{pick("Refreshing...", "ახლდება...")}</span>
          ) : (
            <span>{pick(`${adminSummary?.active_fleet_count ?? 0} active fleets`, `${adminSummary?.active_fleet_count ?? 0} აქტიური ფლიტი`)}</span>
          )}
          <span>{summary?.fleet_name ?? instructions?.fleet_name ?? pick("Active fleet", "აქტიური ფლიტი")}</span>
        </div>
      </section>

      {error ? <p className="statusError">{error}</p> : null}

      {alerts.length ? (
        <section className="ownerAlerts">
          {alerts.map((alert) => (
            <Link key={alert.key} className={`card ownerAlertCard ownerAlert${alert.tone}`} to={alert.to}>
              <div className="ownerAlertEyebrow">{alert.title}</div>
              <div className="txSub">{alert.detail}</div>
              <div className="ownerAlertAction">{alert.cta}</div>
            </Link>
          ))}
        </section>
      ) : null}

      <section className="ownerStatsGrid" aria-label={pick("Admin overview", "ადმინისტრატორის მიმოხილვა")}>
        <button
          className={`card ownerStatCard ownerStatCardButton ${showWithdrawnBreakdown ? "ownerStatCardAccent" : ""}`.trim()}
          type="button"
          onClick={() => setShowWithdrawnBreakdown((current) => !current)}
          aria-expanded={showWithdrawnBreakdown}
        >
          <div className="ownerStatLabel">{pick("Total withdrawn", "ჯამურად გატანილია")}</div>
          <div className="ownerStatValue">{formatMoney(adminSummary?.total_withdrawn ?? "0.00", adminCurrency)}</div>
          <div className="ownerStatSub">
            {pick(
              `${adminSummary?.completed_withdrawal_transactions ?? 0} transactions`,
              `${adminSummary?.completed_withdrawal_transactions ?? 0} ტრანზაქცია`
            )}
          </div>
        </button>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("Total fees", "ჯამური საკომისიო")}</div>
          <div className="ownerStatValue">{formatMoney(adminSummary?.total_fees ?? "0.00", adminCurrency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("Pending payouts", "მოლოდინში მყოფი გატანები")}</div>
          <div className="ownerStatValue">{adminSummary?.pending_payouts_count ?? 0}</div>
          <div className="ownerStatSub">
            {formatMoney(adminSummary?.pending_payouts_total ?? "0.00", adminCurrency)}
          </div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("All fleets", "ყველა ფლიტი")}</div>
          <div className="ownerStatValue">{adminSummary?.fleet_count ?? 0}</div>
          <div className="ownerStatSub">
            {pick(
              `${adminSummary?.active_fleet_count ?? 0} active right now`,
              `ახლა აქტიურია ${adminSummary?.active_fleet_count ?? 0}`
            )}
          </div>
        </article>
      </section>

      {showWithdrawnBreakdown ? (
        <section className="card">
          <div className="cardTitleRow">
            <h2 className="h2">{pick("Withdrawn by fleet", "ფლიტების მიხედვით გატანილი თანხა")}</h2>
            <div className="txSub">
              {pick("Most transactions appear first.", "ყველაზე მეტი ტრანზაქციის მქონე ფლიტები ზემოთ ჩანს.")}
            </div>
          </div>

          <div className="txList" role="list">
            {adminSummary?.withdrawn_by_fleet.length ? (
              adminSummary.withdrawn_by_fleet.map((fleet) => (
                <div key={fleet.fleet_id} className="txRow" role="listitem">
                  <div className="txMain">
                    <div className="txTitle">{fleet.fleet_name}</div>
                    <div className="txSub">
                      {pick(
                        `${fleet.transaction_count} transactions`,
                        `${fleet.transaction_count} ტრანზაქცია`
                      )}
                    </div>
                  </div>
                  <div className="txAmount">{formatMoney(fleet.total_withdrawn, adminCurrency)}</div>
                </div>
              ))
            ) : (
              <div className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">{pick("No completed withdrawals yet", "დასრულებული გატანები ჯერ არ არის")}</div>
                  <div className="txSub">{pick("Fleet totals will show up here after the first completed payouts land.", "ფლიტების ჯამები აქ გამოჩნდება მას შემდეგ, რაც პირველი დასრულებული გატანები დაფიქსირდება.")}</div>
                </div>
              </div>
            )}
          </div>
        </section>
      ) : null}

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Deposit instructions", "შევსების ინსტრუქცია")}</h2>
          <Link className="btn btnGhost" to="/deposits">
            {pick("Open deposits", "შევსებების გახსნა")}
          </Link>
        </div>

        {instructions ? (
          <div className="txList" role="list">
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("Use this exact fleet reference", "გამოიყენეთ ზუსტად ეს ფლიტის კოდი")}</div>
                <div className="txSub mappingCode">{instructions.reference_code}</div>
                <div className="txSub">{pick("Put it in the bank transfer comment so the money can be matched to this fleet.", "ჩაწერეთ ეს საბანკო გადარიცხვის კომენტარში, რომ თანხა ამ ფლიტს მიებას.")}</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("Send funds to this company account", "გადარიცხეთ თანხა ამ კომპანიის ანგარიშზე")}</div>
                <div className="txSub">{instructions.account_holder_name || pick("Company account", "კომპანიის ანგარიში")}</div>
                <div className="txSub">{instructions.account_number}</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("What happens next", "შემდეგ რა ხდება")}</div>
                <div className="txSub">{pick("Your fleet reserve updates after ExpertPay syncs BoG activity and matches the transfer to this reference.", "ფლიტის რეზერვი განახლდება მას შემდეგ, რაც ExpertPay სინქავს BoG აქტივობას და ამ კოდს გადარიცხვას მიაბამს.")}</div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Pending payouts", "მოლოდინში მყოფი გატანები")}</h2>
          <Link className="btn btnGhost" to="/payouts">
            {pick("Open payouts", "გატანების გახსნა")}
          </Link>
        </div>

        <div className="txList" role="list">
          {adminSummary?.pending_by_fleet.length ? (
            adminSummary.pending_by_fleet.map((item) => {
              const isOpen = openPendingFleetId === item.fleet_id;
              return (
                <div key={item.fleet_id} className={`txRow ownerAdminPendingRow ${isOpen ? "ownerAdminPendingRowOpen" : ""}`.trim()} role="listitem">
                  <div className="txMain">
                    <div className="txTitle">{item.fleet_name}</div>
                    <div className="txSub">
                      {pick(
                        `${item.transaction_count} transactions`,
                        `${item.transaction_count} ტრანზაქცია`
                      )}
                    </div>
                    {isOpen ? (
                      <div className="ownerAdminPendingDetails">
                        <div className="ownerAdminPendingDetailLine">
                          <span>{pick("Money left", "დარჩენილი თანხა")}</span>
                          <strong>{formatMoney(item.reserve_balance, adminCurrency)}</strong>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="ownerAdminPendingSide">
                    <div className="txAmount">{formatMoney(item.pending_total, adminCurrency)}</div>
                    <button
                      className="btn btnGhost ownerAdminPendingButton"
                      type="button"
                      onClick={() => setOpenPendingFleetId((current) => (current === item.fleet_id ? null : item.fleet_id))}
                    >
                      {pick("Details", "დეტალები")}
                    </button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("No pending payouts", "მოლოდინში მყოფი გატანები არ არის")}</div>
                <div className="txSub">{pick("Fleet-level pending payout totals will show here as soon as withdrawals queue up.", "ფლიტების მიხედვით მოლოდინში მყოფი გატანების ჯამები აქ გამოჩნდება, როგორც კი რიგი შეიქმნება.")}</div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Recent funding", "ბოლო შევსებები")}</h2>
          {isOwnerAdmin ? (
            <Link className="btn btnGhost" to="/deposit-review">
              {pick("Review queue", "განხილვის რიგი")}
            </Link>
          ) : null}
        </div>

        <div className="txList" role="list">
          {deposits.length ? (
            deposits.map((deposit) => (
              <div key={deposit.id} className="txRow" role="listitem">
                <div className="txMain">
                <div className="txTitle">{formatMoney(deposit.amount, deposit.currency)}</div>
                <div className="txSub">{deposit.payer_name || deposit.reference_code}</div>
                <div className="txSub">{pick("Reference", "კოდი")} {deposit.reference_code}</div>
                <div className="txSub">{deposit.completed_at}</div>
              </div>
              <div className="txAmount pos">{pick("Credited", "ჩარიცხულია")}</div>
            </div>
          ))
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("No deposits yet", "შევსებები ჯერ არ არის")}</div>
                <div className="txSub">{pick("Once transfers are matched to this fleet, funding will show here.", "როგორც კი გადარიცხვები ამ ფლიტს მიება, შევსებები აქ გამოჩნდება.")}</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {isOwnerAdmin ? (
        <section className="ownerQuickLinks">
          <Link className="card ownerLinkCard" to="/fleet-members">
            <div className="ownerLinkEyebrow">{pick("Team", "გუნდი")}</div>
            <div className="txTitle">{pick("Manage drivers and roles", "მძღოლებისა და როლების მართვა")}</div>
            <div className="txSub">{pick("Update access and keep fleet membership current.", "განაახლეთ წვდომები და ფლიტის შემადგენლობა აქტუალური შეინარჩუნეთ.")}</div>
          </Link>
          <Link className="card ownerLinkCard" to="/deposits">
            <div className="ownerLinkEyebrow">{pick("Funding", "შევსება")}</div>
            <div className="txTitle">{pick("Fund fleet reserve", "ფლიტის რეზერვის შევსება")}</div>
            <div className="txSub">{pick("Use your fleet reference and confirm recent funding landed as expected.", "გამოიყენეთ ფლიტის კოდი და გადაამოწმეთ, რომ ბოლო შევსება სწორად ჩაირიცხა.")}</div>
          </Link>
          <Link className="card ownerLinkCard" to="/payouts">
            <div className="ownerLinkEyebrow">{pick("Payouts", "გატანები")}</div>
            <div className="txTitle">{pick("Track payout progress", "გატანის პროგრესის ნახვა")}</div>
            <div className="txSub">{pick("Review payout states, destinations, and any failures that need action.", "ნახეთ გატანის სტატუსები, მიმღებები და შეცდომები, რომლებიც რეაგირებას საჭიროებს.")}</div>
          </Link>
        </section>
      ) : null}

      {isOwnerAdmin ? (
        <section className="ownerInternalTools">
          <div className="cardTitleRow">
            <h2 className="h2">{pick("Internal tools", "შიდა ინსტრუმენტები")}</h2>
            <div className="txSub">{pick("Open these only when you need review, diagnostics, or mapping fixes.", "გახსენით მხოლოდ მაშინ, როცა საჭიროა განხილვა, დიაგნოსტიკა ან მიბმების გასწორება.")}</div>
          </div>

          <div className="ownerQuickLinks">
            <Link className="card ownerLinkCard" to="/deposit-review">
              <div className="ownerLinkEyebrow">{pick("Deposit review", "შევსებების განხილვა")}</div>
              <div className="txTitle">{pick("Match incoming transfers", "შემოსული გადარიცხვების მიბმა")}</div>
              <div className="txSub">{pick("Resolve unmatched bank transfers and backfill missed funding when needed.", "საჭიროებისას დააბით დაუდგენელი გადარიცხვები და backfill-ით აღადგინეთ გამოტოვებული შევსებები.")}</div>
            </Link>
            <Link className="card ownerLinkCard" to="/driver-mappings">
              <div className="ownerLinkEyebrow">{pick("Driver mappings", "მძღოლების მიბმები")}</div>
              <div className="txTitle">{pick("Review Yandex driver links", "Yandex მძღოლების მიბმების განხილვა")}</div>
              <div className="txSub">{pick("Keep fleet earnings attached to the correct driver accounts.", "ფლიტის შემოსავალი სწორ მძღოლის ანგარიშებზე უნდა იყოს მიბმული.")}</div>
            </Link>
            <Link className="card ownerLinkCard" to="/connect-yandex">
              <div className="ownerLinkEyebrow">{pick("Yandex", "Yandex")}</div>
              <div className="txTitle">{pick("Open Yandex operations", "Yandex ოპერაციების გახსნა")}</div>
              <div className="txSub">{pick("Refresh the connection, run syncs, or inspect raw import data only when needed.", "განაახლეთ კავშირი, გაუშვით სინქი ან ნახეთ ნედლი იმპორტის მონაცემები მხოლოდ საჭიროებისას.")}</div>
            </Link>
            <Link className="card ownerLinkCard" to="/settings">
              <div className="ownerLinkEyebrow">{pick("Reconciliation", "შერიგება")}</div>
              <div className="txTitle">{pick("Check treasury health", "საბაზისო ანგარიშის მდგომარეობის შემოწმება")}</div>
              <div className="txSub">{pick("Open the diagnostics view when balances or payout states need deeper review.", "გახსენით დიაგნოსტიკა, როცა ბალანსებს ან გატანის სტატუსებს ღრმა განხილვა სჭირდება.")}</div>
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}
