import { useEffect, useMemo, useRef, useState } from "react";
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

function formatSyncTime(value: string | null | undefined, locale: string, pick: (english: string, georgian: string) => string) {
  if (!value) return pick("Not synced yet", "ჯერ არ დასინქებულა");
  return formatDateTime(value, locale);
}

function driverFullName(row: OwnerDriverFinanceRow) {
  return [row.first_name, row.last_name].filter(Boolean).join(" ").trim() || row.yandex_display_name || row.phone_number;
}

function transactionTypeLabel(value: string, pick: (english: string, georgian: string) => string) {
  if (value === "Deposit") return pick("Deposit", "შევსება");
  if (value === "Withdrawal") return pick("Withdrawal", "გატანა");
  return value;
}

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function SearchGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-4.2-4.2" />
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
  const [ownerSection, setOwnerSection] = useState<"overview" | "drivers" | "payouts">("overview");
  const [showWithdrawnBreakdown, setShowWithdrawnBreakdown] = useState(false);
  const [openPendingFleetId, setOpenPendingFleetId] = useState<number | null>(null);
  const ownerContentRef = useRef<HTMLDivElement | null>(null);

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

    return driverFinanceRows.filter((row) => {
      if (!query) return true;
      const haystack = [
        String(row.id),
        row.first_name,
        row.last_name,
        row.phone_number,
        row.yandex_display_name ?? "",
        row.yandex_phone_number ?? ""
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [driverFinanceRows, financeSearch]);

  const driverBalanceTotal = driverFinanceRows.reduce((total, row) => total + Number(row.available_balance || 0), 0);
  const yandexBalanceTotal = driverFinanceRows.reduce((total, row) => total + Number(row.yandex_current_balance || 0), 0);
  const syncedDriversCount = driverFinanceRows.filter((row) => row.sync_status === "synced" || row.yandex_external_driver_id).length;
  const needsMappingCount = Math.max(driverFinanceRows.length - syncedDriversCount, 0);
  const topDrivers = [...driverFinanceRows]
    .sort((left, right) => Number(right.available_balance || 0) - Number(left.available_balance || 0))
    .slice(0, 5);
  const recentTransactions = ownerTransactions.slice(0, 5);
  const recentPayouts = ownerTransactions
    .filter((row) => row.transaction_type === "Withdrawal")
    .slice(0, 8);
  const latestSyncAt = driverFinanceRows
    .map((row) => row.last_yandex_sync_at)
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0];

  async function handleCopyFleetLink() {
    if (!inviteLink || typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(inviteLink);
    setCopiedLink(true);
    window.setTimeout(() => setCopiedLink(false), 1800);
  }

  function handleOwnerSectionChange(nextSection: "overview" | "drivers" | "payouts") {
    setOwnerSection(nextSection);
    window.setTimeout(() => {
      ownerContentRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  }

  if (isOwner) {
    return (
      <div className="ownerDashboard ownerExecutiveDashboard ownerControlPage">
            <div className="driverInstallAction">
              <InstallAppGuide variant="icon" />
            </div>
            <section className="ownerControlHero">
              <div className="ownerControlHeroCopy">
                <div className="ownerRosterSubtitle">{pick("Fleet control room", "ფლიტის მართვის ოთახი")}</div>
                <h1 className="ownerControlTitle">{activeFleetName || pick("Active fleet", "აქტიური ფლიტი")}</h1>
                <div className="ownerControlHeroBadges">
                  <span className="ownerSyncPill ownerSyncPillGood">
                    {pick("Yandex", "Yandex")} · {formatSyncTime(latestSyncAt, locale, pick)}
                  </span>
                  <span className={`ownerSyncPill ${needsMappingCount ? "ownerSyncPillWarn" : "ownerSyncPillGood"}`}>
                    {needsMappingCount
                      ? pick(`${needsMappingCount} need mapping`, `${needsMappingCount} საჭიროებს მიბმას`)
                      : pick("All drivers mapped", "ყველა მძღოლი მიბმულია")}
                  </span>
                </div>
              </div>
            </section>

            {error ? <p className="statusError">{formatApiError(error)}</p> : null}

            <section className="ownerControlStats" aria-label={pick("Fleet overview", "ფლიტის მიმოხილვა")}>
              <article className="ownerControlStat ownerControlStatPrimary">
                <span>{pick("Available to drivers", "მძღოლებისთვის ხელმისაწვდომი")}</span>
                <strong>{formatMoney(String(driverBalanceTotal), currency)}</strong>
                <small>{pick(`${driverFinanceRows.length} active drivers`, `${driverFinanceRows.length} აქტიური მძღოლი`)}</small>
              </article>
              <article className="ownerControlStat">
                <span>{pick("Fleet reserve", "ფლიტის რეზერვი")}</span>
                <strong>{formatMoney(summary?.reserve_balance ?? "0.00", currency)}</strong>
                <small>{pick("Money currently funded in ExpertPay", "ExpertPay-ში მიმდინარე შევსებული თანხა")}</small>
              </article>
              <article className="ownerControlStat">
                <span>{pick("Pending payouts", "მოლოდინში გატანები")}</span>
                <strong>{formatMoney(summary?.pending_payouts_total ?? "0.00", currency)}</strong>
                <small>{pick(`${summary?.pending_payouts_count ?? 0} requests`, `${summary?.pending_payouts_count ?? 0} მოთხოვნა`)}</small>
              </article>
              <article className="ownerControlStat">
                <span>{pick("Yandex balance", "Yandex ბალანსი")}</span>
                <strong>{formatMoney(String(yandexBalanceTotal), currency)}</strong>
                <small>{pick(`${syncedDriversCount} synced drivers`, `${syncedDriversCount} დასინქებული მძღოლი`)}</small>
              </article>
            </section>

            <nav className="ownerControlTabs" aria-label={pick("Owner dashboard sections", "მფლობელის დეშბორდის სექციები")}>
              <button className={`ownerControlTab ${ownerSection === "overview" ? "ownerControlTabActive" : ""}`} type="button" onClick={() => handleOwnerSectionChange("overview")}>
                {pick("Overview", "მიმოხილვა")}
              </button>
              <button className={`ownerControlTab ${ownerSection === "drivers" ? "ownerControlTabActive" : ""}`} type="button" onClick={() => handleOwnerSectionChange("drivers")}>
                {pick("Drivers", "მძღოლები")}
              </button>
              <button className={`ownerControlTab ${ownerSection === "payouts" ? "ownerControlTabActive" : ""}`} type="button" onClick={() => handleOwnerSectionChange("payouts")}>
                {pick("Payouts", "გატანები")}
              </button>
            </nav>

            <div ref={ownerContentRef} className="ownerSectionContent">
            {ownerSection === "overview" ? (
              <div className="ownerControlGrid">
                <section className="ownerControlPanel ownerAttentionPanel">
                  <div className="ownerControlPanelHeader">
                    <div>
                      <h2>{pick("Needs attention", "საყურადღებო")}</h2>
                      <p>{pick("The few things worth checking first.", "პირველ რიგში გადასამოწმებელი საკითხები.")}</p>
                    </div>
                    <button className="ownerTinyButton" type="button" onClick={() => void loadData()}>
                      {pick("Refresh", "განახლება")}
                    </button>
                  </div>
                  <div className="ownerAttentionList">
                    {needsMappingCount ? (
                      <Link className="ownerAttentionItem ownerAttentionWarn" to="/driver-mappings">
                        <strong>{pick("Driver mapping needed", "მძღოლის მიბმა საჭიროა")}</strong>
                        <span>{pick(`${needsMappingCount} drivers are not linked to Yandex yet.`, `${needsMappingCount} მძღოლი ჯერ არ არის მიბმული Yandex-ზე.`)}</span>
                      </Link>
                    ) : null}
                    {alerts.length ? (
                      alerts.slice(0, 3).map((alert) => (
                        <Link key={alert.key} className={`ownerAttentionItem ownerAttention${alert.tone}`} to={alert.to}>
                          <strong>{alert.title}</strong>
                          <span>{alert.detail}</span>
                        </Link>
                      ))
                    ) : !needsMappingCount ? (
                      <div className="ownerAttentionItem ownerAttentionGood">
                        <strong>{pick("Everything looks clean", "ყველაფერი წესრიგშია")}</strong>
                        <span>{pick("No urgent fleet issues right now.", "ამ მომენტში სასწრაფო პრობლემა არ ჩანს.")}</span>
                      </div>
                    ) : null}
                  </div>
                </section>

                <section className="ownerControlPanel">
                  <div className="ownerControlPanelHeader">
                    <div>
                      <h2>{pick("Top driver balances", "ყველაზე მაღალი ბალანსები")}</h2>
                      <p>{pick("Drivers most likely to request a payout next.", "მძღოლები, ვინც შესაძლოა შემდეგ მოითხოვონ გატანა.")}</p>
                    </div>
                    <button className="ownerTinyButton" type="button" onClick={() => handleOwnerSectionChange("drivers")}>
                      {pick("View all", "ყველას ნახვა")}
                    </button>
                  </div>
                  <div className="ownerMiniList">
                    {topDrivers.length ? (
                      topDrivers.map((row) => (
                        <div key={row.id} className="ownerMiniRow">
                          <div>
                            <strong>{driverFullName(row)}</strong>
                            <span>{row.phone_number}</span>
                          </div>
                          <b>{formatMoney(row.available_balance, row.currency)}</b>
                        </div>
                      ))
                    ) : (
                      <div className="ownerEmptyState">{pick("No drivers yet.", "მძღოლები ჯერ არ არის.")}</div>
                    )}
                  </div>
                </section>

                <section className="ownerControlPanel ownerControlPanelWide">
                  <div className="ownerControlPanelHeader">
                    <div>
                      <h2>{pick("Recent movement", "ბოლო მოძრაობა")}</h2>
                      <p>{pick("Funding and payout activity for this fleet.", "ამ ფლიტის შევსებები და გატანები.")}</p>
                    </div>
                    <button className="ownerTinyButton" type="button" onClick={() => handleOwnerSectionChange("payouts")}>
                      {pick("Details", "დეტალები")}
                    </button>
                  </div>
                  <div className="ownerMovementList">
                    {recentTransactions.length ? (
                      recentTransactions.map((row) => (
                        <div key={row.id} className="ownerMovementRow">
                          <span className={row.transaction_type === "Deposit" ? "ownerMovementIcon ownerMovementIconDeposit" : "ownerMovementIcon"}>
                            {row.transaction_type === "Deposit" ? "+" : "-"}
                          </span>
                          <div>
                            <strong>{transactionTypeLabel(row.transaction_type, pick)}</strong>
                            <span>{formatDateTime(row.created_at, locale)}</span>
                          </div>
                          <b>{formatMoney(row.amount, row.currency)}</b>
                        </div>
                      ))
                    ) : (
                      <div className="ownerEmptyState">{pick("No fleet transactions yet.", "ფლიტის ტრანზაქციები ჯერ არ არის.")}</div>
                    )}
                  </div>
                </section>
              </div>
            ) : ownerSection === "drivers" ? (
              <>
                <section className="ownerControlPanel">
                  <div className="ownerControlPanelHeader ownerDriversHeader">
                    <div>
                      <h2>{pick("Drivers", "მძღოლები")}</h2>
                      <p>{pick("Search, compare Yandex balance, and see what is available in ExpertPay.", "მოძებნეთ, შეადარეთ Yandex ბალანსი და ნახეთ ExpertPay-ში ხელმისაწვდომი თანხა.")}</p>
                    </div>
                    <div className="ownerInviteCopy">
                      <input className="ownerRosterInput ownerRosterInputLink" type="text" readOnly value={inviteLink} />
                      <button className="ownerRosterCopyButton" type="button" onClick={() => void handleCopyFleetLink()} aria-label={pick("Copy fleet link", "ფლიტის ლინკის დაკოპირება")}>
                        <CopyGlyph />
                      </button>
                      {copiedLink ? <span>{pick("Copied", "დაკოპირდა")}</span> : null}
                    </div>
                  </div>
                  <div className="ownerRosterSearchRow ownerControlSearchRow">
                    <label className="ownerRosterField ownerRosterFieldGrow">
                      <input
                        className="ownerRosterInput"
                        type="text"
                        placeholder={pick("Search by name, phone, or Yandex name", "ძებნა სახელით, ნომრით ან Yandex სახელით")}
                        value={financeSearch}
                        onChange={(event) => setFinanceSearch(event.target.value)}
                      />
                    </label>
                    <button className="ownerRosterActionButton" type="button" onClick={() => void loadData()} aria-label={pick("Refresh drivers", "მძღოლების განახლება")}>
                      <SearchGlyph />
                    </button>
                  </div>
                </section>

                <section className="ownerDriverCards">
                  {filteredFinanceRows.length ? (
                    filteredFinanceRows.map((row) => {
                      const isSynced = row.sync_status === "synced" || Boolean(row.yandex_external_driver_id);
                      return (
                        <article key={row.id} className="ownerDriverCard">
                          <div className="ownerDriverCardTop">
                            <div>
                              <h3>{driverFullName(row)}</h3>
                              <p>{row.phone_number}</p>
                            </div>
                            <span className={`ownerDriverSync ${isSynced ? "ownerDriverSyncGood" : "ownerDriverSyncWarn"}`}>
                              {isSynced ? pick("Synced", "დასინქებულია") : pick("Needs mapping", "საჭიროებს მიბმას")}
                            </span>
                          </div>
                          <div className="ownerDriverMoneyGrid">
                            <div>
                              <span>{pick("ExpertPay", "ExpertPay")}</span>
                              <strong>{formatMoney(row.available_balance, row.currency)}</strong>
                            </div>
                            <div>
                              <span>{pick("Yandex", "Yandex")}</span>
                              <strong>{formatMoney(row.yandex_current_balance ?? "0.00", row.yandex_balance_currency ?? row.currency)}</strong>
                            </div>
                            <div>
                              <span>{pick("Trips / rows", "ტრანზაქციები")}</span>
                              <strong>{row.transaction_count}</strong>
                            </div>
                          </div>
                          <div className="ownerDriverFooter">
                            <span>{pick("Last sync", "ბოლო სინქი")}: {formatSyncTime(row.last_yandex_sync_at, locale, pick)}</span>
                            {row.yandex_display_name ? <span>{row.yandex_display_name}</span> : null}
                          </div>
                        </article>
                      );
                    })
                  ) : (
                    <div className="ownerControlPanel ownerEmptyState">{pick("No drivers match that search.", "ამ ძიებით მძღოლები ვერ მოიძებნა.")}</div>
                  )}
                </section>
              </>
            ) : (
              <section className="ownerControlPanel">
                <div className="ownerControlPanelHeader">
                  <div>
                    <h2>{pick("Payouts", "გატანები")}</h2>
                    <p>{pick("Track withdrawal requests and recent fleet movement.", "ნახეთ გატანის მოთხოვნები და ფლიტის ბოლო მოძრაობა.")}</p>
                  </div>
                  <Link className="ownerTinyButton" to="/payouts">
                    {pick("Open bank queue", "ბანკის რიგის გახსნა")}
                  </Link>
                </div>

                <div className="ownerPayoutCards">
                  {summary?.pending_payouts.length ? (
                    summary.pending_payouts.map((payout) => (
                      <div key={payout.id} className="ownerPayoutCard">
                        <span className="ownerPayoutIcon">⌛</span>
                        <div>
                          <strong>{payout.driver_name || pick("Driver payout", "მძღოლის გატანა")}</strong>
                          <span>{pick("Waiting for bank/signing", "ელოდება ბანკს/ხელმოწერას")}</span>
                        </div>
                        <b>{formatMoney(payout.amount, payout.currency)}</b>
                      </div>
                    ))
                  ) : recentPayouts.length ? (
                    recentPayouts.map((row) => (
                      <div key={row.id} className="ownerPayoutCard">
                        <span className="ownerPayoutIcon ownerPayoutIconDone">✓</span>
                        <div>
                          <strong>{transactionTypeLabel(row.transaction_type, pick)}</strong>
                          <span>{formatDateTime(row.created_at, locale)}</span>
                        </div>
                        <b>{formatMoney(row.amount, row.currency)}</b>
                      </div>
                    ))
                  ) : (
                    <div className="ownerEmptyState">{pick("No payout requests yet.", "გატანის მოთხოვნები ჯერ არ არის.")}</div>
                  )}
                </div>
              </section>
            )}
            </div>
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
