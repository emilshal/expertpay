import { useEffect, useState } from "react";
import {
  bankAccounts,
  createBankAccount,
  createWithdrawal,
  getActiveFleetName,
  walletBalance,
  withdrawalsList,
  type BankAccount,
  type WithdrawalItem
} from "../lib/api";
import InstallAppGuide from "../components/InstallAppGuide";
import { useI18n } from "../lib/i18n";

type PickFn = (english: string, georgian: string) => string;

function formatApiError(error: unknown, pick: PickFn) {
  if (!(error instanceof Error)) return pick("Request failed.", "მოთხოვნა ვერ შესრულდა.");
  const raw = error.message?.trim();
  if (!raw) return pick("Request failed.", "მოთხოვნა ვერ შესრულდა.");

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

function friendlyWithdrawalError(error: unknown, pick: PickFn) {
  const message = formatApiError(error, pick);
  if (message.includes("Insufficient driver available balance")) {
    return pick("You do not have enough withdrawable earnings for this request yet.", "ამ მოთხოვნისთვის საკმარისი გასატანი შემოსავალი ჯერ არ გაქვთ.");
  }
  if (message.includes("Insufficient fleet reserve balance")) {
    return pick("Your fleet does not have enough reserve funding right now. Please ask your fleet owner to top up the reserve.", "თქვენს ფლიტს ახლა საკმარისი რეზერვი არ აქვს. სთხოვეთ ფლიტის მფლობელს რეზერვის შევსება.");
  }
  if (message.includes("Bank account not found")) {
    return pick("Choose a saved bank account before requesting a payout.", "გატანის მოთხოვნამდე აირჩიეთ შენახული საბანკო ანგარიში.");
  }
  if (message.includes("Minimum withdrawal amount")) {
    return pick("Minimum withdrawal amount is 1.00 GEL.", "გატანის მინიმალური თანხაა 1.00 GEL.");
  }
  if (message.includes("Maximum withdrawal amount")) {
    return pick("Maximum withdrawal amount is 500.00 GEL.", "გატანის მაქსიმალური თანხაა 500.00 GEL.");
  }
  if (message.includes("Only Bank of Georgia accounts are allowed right now")) {
    return pick("Only Bank of Georgia accounts with GE..BG.. are allowed right now.", "ახლა დაშვებულია მხოლოდ Bank of Georgia-ს ანგარიშები GE..BG.. ფორმატით.");
  }
  if (message.includes("before requesting another withdrawal")) {
    return pick("Please wait 5 minutes before requesting another withdrawal.", "შემდეგი გატანის მოთხოვნამდე დაელოდეთ 5 წუთი.");
  }
  return message;
}

function withdrawalStatusLabel(status: WithdrawalItem["status"], pick: PickFn) {
  if (status === "pending") return pick("Requested", "მოთხოვნილია");
  if (status === "processing") return pick("Processing", "მუშავდება");
  if (status === "completed") return pick("Completed", "დასრულდა");
  if (status === "failed") return pick("Failed", "ვერ შესრულდა");
  return status;
}

function formatDateTime(value: string, locale: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const normalizedLocale = locale === "ka-GE" ? "ka-GE" : "en-GB";
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
  if (Number.isNaN(date.getTime())) return value;
  const normalizedLocale = locale === "ka-GE" ? "ka-GE" : "en-GB";
  return new Intl.DateTimeFormat(normalizedLocale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function fleetRatingTier(value: string) {
  const numericValue = Number.parseFloat(value);
  if (!Number.isFinite(numericValue)) return "bronze";
  if (numericValue <= 0) return "bronze";
  if (numericValue >= 4) return "gold";
  if (numericValue >= 3) return "silver";
  return "bronze";
}

function visualWithdrawalStatus(item: WithdrawalItem, nowMs: number): WithdrawalItem["status"] {
  if (item.status !== "processing" && item.status !== "pending") return item.status;
  const createdAt = new Date(item.created_at).getTime();
  if (Number.isNaN(createdAt)) return item.status;
  return nowMs - createdAt >= 60_000 ? "completed" : item.status;
}

function normalizeIban(value: string) {
  return value.replace(/\s+/g, "").toUpperCase();
}

function isBogIban(value: string) {
  return /^GE\d{2}BG[A-Z0-9]+$/.test(normalizeIban(value));
}

function prefilledWithdrawalAmount(balanceValue: string) {
  const numericBalance = Number.parseFloat(balanceValue);
  if (!Number.isFinite(numericBalance) || numericBalance <= 0) return "1.00";
  return Math.min(numericBalance, 500).toFixed(2);
}

function formatMoney(value: string | number, locale: string) {
  const numericValue = typeof value === "number" ? value : Number.parseFloat(value);
  if (!Number.isFinite(numericValue)) return String(value);
  const normalizedLocale = locale === "ka-GE" ? "en-US" : "en-US";
  return new Intl.NumberFormat(normalizedLocale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(numericValue);
}

function formatDriverReward(reward: string | null | undefined, pick: PickFn) {
  if (reward === "5 free withdrawals") {
    return pick("5 free withdrawals", "5 უფასო გატანა");
  }
  return pick("No reward yet", "ჯილდო ჯერ არ არის");
}

export default function DriverDashboardPage() {
  const { pick, locale } = useI18n();
  const [driverName, setDriverName] = useState(pick("Driver", "მძღოლი"));
  const [driverLevel, setDriverLevel] = useState(1);
  const [driverReward, setDriverReward] = useState("No reward yet");
  const [balance, setBalance] = useState("0.00");
  const [currency, setCurrency] = useState("GEL");
  const [fleetRating, setFleetRating] = useState("0.0");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
  const [loadingData, setLoadingData] = useState(false);
  const [isWithdrawOpen, setWithdrawOpen] = useState(false);
  const [selectedWithdrawal, setSelectedWithdrawal] = useState<WithdrawalItem | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  async function loadData() {
    setLoadingData(true);
    try {
      const [balanceData, accountData, withdrawalData] = await Promise.all([
        walletBalance(),
        bankAccounts(),
        withdrawalsList()
      ]);
      setDriverName(balanceData.driver_name ?? pick("Driver", "მძღოლი"));
      setDriverLevel(balanceData.driver_level ?? 1);
      setDriverReward(balanceData.driver_reward ?? "No reward yet");
      setBalance(balanceData.balance);
      setCurrency(balanceData.currency);
      setFleetRating(balanceData.fleet_rating ?? "0.0");
      setAccounts(accountData);
      setWithdrawals(withdrawalData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingData(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 10_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const formattedBalance = formatMoney(balance || 0, locale);
  const fleetName = getActiveFleetName() ?? pick("Taxi Fleet", "ტაქსის ფლიტი");
  const ratingTier = fleetRatingTier(fleetRating);
  const hasOpenModal = isWithdrawOpen || selectedWithdrawal !== null;

  useEffect(() => {
    if (!hasOpenModal) return;

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
  }, [hasOpenModal]);

  return (
    <div className="dashboard">
      <div className="driverInstallAction">
        <InstallAppGuide variant="icon" />
      </div>
      <section className="card driverProgressCard">
        <div className="driverProgressName">{driverName}</div>
        <div className="driverProgressMeta">
          <div>
            <div className="driverProgressLabel">{pick("Level", "დონე")}</div>
            <div className="driverProgressValue">{driverLevel}</div>
          </div>
          <div>
            <div className="driverProgressLabel">{pick("Reward", "ჯილდო")}</div>
            <div className="driverProgressReward">{formatDriverReward(driverReward, pick)}</div>
          </div>
        </div>
      </section>

      <section className="card balanceCard">
        <div className="balanceHeader">
          <div>
            <div className="driverFleetMeta">
              <span className="driverFleetName">{fleetName}</span>
              <span className={`driverFleetRating driverFleetRating${ratingTier[0].toUpperCase()}${ratingTier.slice(1)}`}>
                <IconStar />
                {fleetRating}
              </span>
            </div>
            <div className="muted">{pick("Your balance", "თქვენი ბალანსი")}</div>
            <div className="balanceValue">
              {formattedBalance} {currency}
            </div>
          </div>
          <div style={{ display: "grid", justifyItems: "end", gap: 8 }}>
            <button className="transferSubmit" type="button" onClick={() => setWithdrawOpen(true)}>
              {pick("Withdraw Amount", "თანხის გატანა")}
            </button>
            {loadingData ? <div className="muted">{pick("Syncing...", "სინქდება...")}</div> : null}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Payout history", "გატანის ისტორია")}</h2>
        </div>

        <div className="txList" role="list">
          {withdrawals.length ? (
            withdrawals.map((item) => {
              const displayStatus = visualWithdrawalStatus(item, nowMs);
              return (
                <div key={item.id} className="txRow" role="listitem">
                  <div className="txStatusVisual" aria-label={withdrawalStatusLabel(displayStatus, pick)}>
                    <span className="txStatusVisualMain" aria-hidden="true">
                      <IconWithdraw />
                    </span>
                    <span
                      className={`txStatusBadge ${displayStatus === "completed" ? "txStatusBadgeSuccess" : displayStatus === "failed" ? "txStatusBadgeFailed" : "txStatusBadgePending"}`}
                      aria-hidden="true"
                    >
                      {displayStatus === "completed" ? <IconCheckmark /> : displayStatus === "failed" ? <IconCloseSmall /> : <IconHourglass />}
                    </span>
                  </div>
                  <div className="txMain">
                    <div className="txTitle">
                      {formatMoney(item.amount, locale)} {item.currency}
                    </div>
                    <div className="txMetaColumn">
                      <div className="txMetaPrimary">{item.bank_account.beneficiary_name}</div>
                      <div className="txSub">{formatDateOnly(item.created_at, locale)}</div>
                      <div className="txSub">{formatTimeOnly(item.created_at, locale)}</div>
                    </div>
                  </div>
                  <button className="txInlineAction" type="button" onClick={() => setSelectedWithdrawal(item)}>
                    {pick("Details", "დეტალები")}
                  </button>
                </div>
              );
            })
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("No payouts yet", "გატანები ჯერ არ არის")}</div>
                <div className="txSub">{pick("Your requested, processing, completed, and failed payouts will appear here.", "აქ გამოჩნდება თქვენი მოთხოვნილი, დამუშავებადი, დასრულებული და წარუმატებელი გატანები.")}</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {isWithdrawOpen ? (
        <WithdrawModal
          pick={pick}
          availableBalance={balance}
          bankAccounts={accounts}
          onClose={() => setWithdrawOpen(false)}
          onCreated={async () => {
            await loadData();
          }}
        />
      ) : null}

      {selectedWithdrawal ? (
        <WithdrawalDetailsModal
          pick={pick}
          locale={locale}
          item={selectedWithdrawal}
          displayStatus={visualWithdrawalStatus(selectedWithdrawal, nowMs)}
          onClose={() => setSelectedWithdrawal(null)}
        />
      ) : null}
    </div>
  );
}

function WithdrawModal({
  pick,
  availableBalance,
  bankAccounts,
  onClose,
  onCreated
}: {
  pick: PickFn;
  availableBalance: string;
  bankAccounts: BankAccount[];
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const withdrawalFee = 0.5;
  const previousFee = 1;
  const savedBogAccount =
    bankAccounts.find((item) => item.bank_name.toLowerCase() === "bank of georgia") ?? null;
  const [savedBankId, setSavedBankId] = useState<number | null>(savedBogAccount?.id ?? null);
  const [accountNumber, setAccountNumber] = useState(savedBogAccount?.account_number ?? "");
  const [beneficiaryName, setBeneficiaryName] = useState(savedBogAccount?.beneficiary_name ?? "");
  const [beneficiaryInn, setBeneficiaryInn] = useState(savedBogAccount?.beneficiary_inn ?? "");
  const [amount, setAmount] = useState(() => prefilledWithdrawalAmount(availableBalance));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<{
    bankName: string;
    beneficiaryName: string;
    accountNumber: string;
    amount: string;
    fee: string;
    payoutAmount: string;
  } | null>(null);

  const numericAmount = Number(amount || 0);
  const payoutAmount = Number.isFinite(numericAmount) && numericAmount > 0 ? Math.max(numericAmount - withdrawalFee, 0) : 0;

  async function submit() {
    setLoading(true);
    setError("");
    try {
      if (!Number.isFinite(numericAmount) || numericAmount < 1) {
        throw new Error("Minimum withdrawal amount is 1.00 GEL.");
      }
      if (numericAmount > 500) {
        throw new Error("Maximum withdrawal amount is 500.00 GEL.");
      }
      if (!isBogIban(accountNumber)) {
        throw new Error("Only Bank of Georgia accounts are allowed right now.");
      }
      let bankId: number;
      if (savedBankId) {
        bankId = savedBankId;
      } else {
        const newAccount = await createBankAccount({
          bank_name: "Bank of Georgia",
          account_number: normalizeIban(accountNumber),
          beneficiary_name: beneficiaryName,
          beneficiary_inn: beneficiaryInn
        });
        bankId = newAccount.id;
        setSavedBankId(newAccount.id);
      }

      await createWithdrawal({ bank_account_id: bankId, amount: payoutAmount.toFixed(2) });
      await onCreated();
      setReceipt({
        bankName: "Bank of Georgia",
        beneficiaryName,
        accountNumber: normalizeIban(accountNumber),
        amount: numericAmount.toFixed(2),
        fee: withdrawalFee.toFixed(2),
        payoutAmount: payoutAmount.toFixed(2)
      });
    } catch (err) {
      const message = friendlyWithdrawalError(err, pick);
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="transferModal"
        role="dialog"
        aria-modal="true"
        aria-label={pick("Withdraw money", "თანხის გატანა")}
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label={pick("Close withdraw", "გატანის დახურვა")} onClick={onClose}>
          <IconClose />
        </button>

        {receipt ? (
          <div className="withdrawReceipt withdrawReceiptSuccess">
            <div className="withdrawReceiptNotice">
              {pick("Success. The request has been sent to the bank.", "წარმატებით. მოთხოვნა ბანკში გაიგზავნა.")}
            </div>
            <h2 className="transferTitle withdrawReceiptTitle">{pick("Withdrawal details", "გატანის დეტალები")}</h2>
            <div className="withdrawReceiptList">
              <div className="withdrawReceiptRow">
                <span className="withdrawReceiptLabel">{pick("Bank", "ბანკი")}</span>
                <strong className="withdrawReceiptValue">{receipt.bankName}</strong>
              </div>
              <div className="withdrawReceiptRow">
                <span className="withdrawReceiptLabel">{pick("Beneficiary", "მიმღები")}</span>
                <strong className="withdrawReceiptValue">{receipt.beneficiaryName}</strong>
              </div>
              <div className="withdrawReceiptRow">
                <span className="withdrawReceiptLabel">{pick("Bank account number", "საბანკო ანგარიშის ნომერი")}</span>
                <strong className="withdrawReceiptValue">{receipt.accountNumber}</strong>
              </div>
              <div className="withdrawReceiptRow">
                <span className="withdrawReceiptLabel">{pick("Amount", "თანხა")}</span>
                <div className="withdrawReceiptAmountRow">
                  <strong className="withdrawReceiptValue">{formatMoney(receipt.amount, "en-US")} GEL</strong>
                  <strong className="withdrawReceiptValue withdrawReceiptCommission">
                    <span className="withdrawReceiptCommissionOld">{formatMoney(previousFee, "en-US")} GEL</span>
                    <span>{formatMoney(receipt.fee, "en-US")} GEL</span>
                  </strong>
                </div>
              </div>
            </div>
            <div className="withdrawReceiptDivider" />
            <div className="withdrawReceiptTotal">
              <span className="withdrawReceiptTotalLabel">{pick("Withdrawal amount", "გასატანი თანხა")}</span>
              <strong className="withdrawReceiptTotalValue">{formatMoney(receipt.payoutAmount, "en-US")} GEL</strong>
            </div>
            <button className="transferSubmit" type="button" onClick={onClose}>
              {pick("Done", "დასრულება")}
            </button>
          </div>
        ) : (
          <form className="transferForm" onSubmit={(event) => event.preventDefault()}>
          <label className="transferField">
            <span className="transferLabel">{pick("Amount to receive", "მისაღები თანხა")}</span>
            <input
              className="transferInput"
              type="text"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              placeholder="1.00 - 500.00"
            />
          </label>

          <div className="driverBankSummary">
            <div className="txSub">{pick("Allowed range", "დაშვებული დიაპაზონი")} 1.00 - 500.00 GEL</div>
          </div>

          <label className="transferField">
            <span className="transferLabel">{pick("Account number", "ანგარიშის ნომერი")}</span>
            <div className="bankInputWrap">
              <input
                className="transferInput transferInputBank"
                type="text"
                placeholder="GE..."
                value={accountNumber}
                onChange={(event) => setAccountNumber(event.target.value.toUpperCase())}
                readOnly={Boolean(savedBankId)}
              />
              <span className="bankInputBrand" aria-hidden="true">
                <IconBogMark />
              </span>
            </div>
          </label>

            <label className="transferField">
              <span className="transferLabel">{pick("Beneficiary name", "მიმღების სახელი")}</span>
              <input
                className="transferInput"
                type="text"
                placeholder={pick("Full name", "სრული სახელი")}
                value={beneficiaryName}
                onChange={(event) => setBeneficiaryName(event.target.value)}
                readOnly={Boolean(savedBankId)}
              />
            </label>

            {!savedBankId ? (
              <label className="transferField">
                <span className="transferLabel">{pick("Beneficiary ID number", "მიმღების პირადი ნომერი")}</span>
                <input
                  className="transferInput"
                  type="text"
                  placeholder={pick("Personal ID", "პირადი ნომერი")}
                  value={beneficiaryInn}
                  onChange={(event) => setBeneficiaryInn(event.target.value)}
                />
              </label>
            ) : null}

            {savedBankId ? (
              <p className="statusHint">
                {pick("Using your last saved Bank of Georgia account.", "გამოიყენება თქვენი ბოლოს შენახული Bank of Georgia-ს ანგარიში.")}
              </p>
            ) : null}

            <button className="transferSubmit" type="button" onClick={() => void submit()}>
              {loading ? pick("Please wait...", "გთხოვთ დაელოდოთ...") : pick("Withdraw Amount", "თანხის გატანა")}
            </button>
            {error ? <p className="statusError">{error}</p> : null}
          </form>
        )}
      </section>
    </div>
  );
}

function WithdrawalDetailsModal({
  pick,
  locale,
  item,
  displayStatus,
  onClose
}: {
  pick: PickFn;
  locale: string;
  item: WithdrawalItem;
  displayStatus: WithdrawalItem["status"];
  onClose: () => void;
}) {
  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="transferModal"
        role="dialog"
        aria-modal="true"
        aria-label={pick("Withdrawal details", "გატანის დეტალები")}
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label={pick("Close details", "დეტალების დახურვა")} onClick={onClose}>
          <IconClose />
        </button>

        <div className="withdrawReceipt">
          <h2 className="transferTitle">{pick("Withdrawal details", "გატანის დეტალები")}</h2>
          <div className="withdrawReceiptStatusRow">
            <span className="txStatusVisual txStatusVisualLarge" aria-hidden="true">
              <span className="txStatusVisualMain">
                <IconWithdraw />
              </span>
              <span
                className={`txStatusBadge ${displayStatus === "completed" ? "txStatusBadgeSuccess" : displayStatus === "failed" ? "txStatusBadgeFailed" : "txStatusBadgePending"}`}
              >
                {displayStatus === "completed" ? <IconCheckmark /> : displayStatus === "failed" ? <IconCloseSmall /> : <IconHourglass />}
              </span>
            </span>
            <div>
              <div className="withdrawReceiptStatusLabel">{withdrawalStatusLabel(displayStatus, pick)}</div>
              <div className="txSub">{formatDateTime(item.created_at, locale)}</div>
            </div>
          </div>
          <div className="withdrawReceiptList">
            <div className="withdrawReceiptRow">
              <span className="withdrawReceiptLabel">{pick("Beneficiary", "მიმღები")}</span>
              <strong className="withdrawReceiptValue">{item.bank_account.beneficiary_name}</strong>
            </div>
            <div className="withdrawReceiptRow">
              <span className="withdrawReceiptLabel">{pick("Bank", "ბანკი")}</span>
              <strong className="withdrawReceiptValue">{item.bank_account.bank_name}</strong>
            </div>
            <div className="withdrawReceiptRow">
              <span className="withdrawReceiptLabel">{pick("Bank account number", "საბანკო ანგარიშის ნომერი")}</span>
              <strong className="withdrawReceiptValue">{item.bank_account.account_number}</strong>
            </div>
            <div className="withdrawReceiptRow">
              <span className="withdrawReceiptLabel">{pick("Amount", "თანხა")}</span>
              <strong className="withdrawReceiptValue">{formatMoney(item.amount, locale)} {item.currency}</strong>
            </div>
            <div className="withdrawReceiptRow">
              <span className="withdrawReceiptLabel">{pick("Commission", "კომისია")}</span>
              <strong className="withdrawReceiptValue">{formatMoney(item.fee_amount || 0, locale)} {item.currency}</strong>
            </div>
          </div>
          <button className="transferSubmit" type="button" onClick={onClose}>
            {pick("Done", "დასრულება")}
          </button>
        </div>
      </section>
    </div>
  );
}

function IconStar() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="m12 4 2.5 5.2 5.8.8-4.2 4.1 1 5.9-5.1-2.7-5.1 2.7 1-5.9L3.7 10l5.8-.8L12 4Z"
        fill="currentColor"
      />
    </svg>
  );
}

function IconWithdraw() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M12 4v10"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="m7.5 10.5 4.5 4.5 4.5-4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M5 19.5h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconHourglass() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
      <path
        d="M6 2h12v2h-1v2.3c0 1.4-.6 2.7-1.6 3.6L13.4 12l2 2.1c1 .9 1.6 2.2 1.6 3.6V20h1v2H6v-2h1v-2.3c0-1.4.6-2.7 1.6-3.6l2-2.1-2-2.1C7.6 9 7 7.7 7 6.3V4H6V2Zm3 2v2.3c0 .8.3 1.6.9 2.1l2.1 2.2 2.1-2.2c.6-.6.9-1.3.9-2.1V4H9Zm6 16v-2.3c0-.8-.3-1.6-.9-2.1l-2.1-2.2-2.1 2.2c-.6.6-.9 1.3-.9 2.1V20h6Z"
        fill="currentColor"
      />
    </svg>
  );
}

function IconCheckmark() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
      <path d="m5 12 4.2 4.2L19 6.8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconCloseSmall() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
      <path d="M8 8l8 8M16 8l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconClose() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconBogMark() {
  return (
    <svg viewBox="0 0 114 97" width="30" height="26" fill="none" aria-hidden="true">
      <path d="M111.018 30.89L99.6178 44.25V69.09C99.6178 82.47 88.7378 93.36 75.3578 93.36H34.1778C26.4078 93.36 19.4878 89.69 15.0478 84C14.2378 84.12 13.3778 84.19 12.4678 84.19C9.51779 84.19 2.10779 82.19 2.10779 77.46C2.10779 75.25 3.90779 73.46 6.11779 73.46C6.79779 73.46 7.33779 73.62 7.79779 73.8C7.79779 73.8 9.92779 74.62 9.92779 73.25V27.91C9.90779 14.53 20.7978 3.64001 34.1678 3.64001H75.3478C98.5478 3.64001 106.528 20.04 111.498 27.32C112.238 28.4 111.858 29.9 111.008 30.89" fill="white"/>
      <path d="M107.218 27.65C105.528 25.31 101.078 18.89 98.1178 16.49C95.6378 14.51 92.7378 13.1 89.0878 13.33C82.7878 13.73 77.5578 19.03 74.2478 22.99C71.6778 26.05 63.7878 30.95 55.3678 33.18C49.0078 34.86 41.8378 34.01 36.1478 33.59C33.0078 33.36 30.1178 33.13 27.6378 33.26C18.6978 33.71 13.3678 40.27 13.5878 47.86C13.8078 55.57 19.1078 62.59 19.1078 69.82C19.1078 75.49 14.4978 78 11.3178 78C7.51778 78 7.25778 76.45 6.10778 76.45C5.63778 76.45 5.09778 76.84 5.09778 77.46C5.09778 79.38 9.79778 81.2 12.4678 81.2C19.5978 81.2 22.5678 76.11 22.5678 76.11C22.5678 76.11 24.3778 81.38 31.4078 81.38C37.0078 81.38 39.4378 78.7 39.4378 76.46C39.4378 74.69 38.5978 74.04 37.8578 73.19C31.9478 67.68 29.9078 63.83 30.9078 60.05C31.9278 56.19 35.9878 53.63 39.0778 53.68C39.0778 53.68 34.8078 56.06 33.9178 60.39C32.9978 64.83 37.7878 69.15 39.0378 69.62C39.0378 69.62 40.3078 69.62 40.6578 69.59C43.8178 69.3 44.8378 67.82 44.8378 66.36C44.8378 64.27 42.3978 64.41 42.3978 60.98C42.3978 58.38 43.8378 57.53 45.1078 57.53C46.4778 57.53 51.6778 58.03 57.9678 58.67C60.0678 58.88 65.3078 60.91 65.3078 69.05V71.98C65.3078 76.94 67.3078 83.08 76.0778 83.08C82.0378 83.08 85.3778 79.76 85.3778 77.36C85.3778 75.79 84.0078 75.1 83.3278 74.16C81.3378 71.38 82.3178 67.51 82.3178 67.51H82.3578C83.1878 67.78 84.1578 67.94 85.2678 67.94C89.6578 67.94 91.7178 66.2 91.7178 64.12C91.7178 61.69 88.4278 61.7 88.0878 59.56C87.6578 56.89 88.3778 45.07 92.9578 38.54L96.5878 40.17C97.1278 40.42 97.7678 40.27 98.1478 39.81L107.168 29.25C107.548 28.79 107.578 28.13 107.228 27.64" fill="#FF6022"/>
      <path d="M22.4578 53.74C20.6978 51.98 19.6078 49.55 19.6078 46.87C19.6078 41.5 24.3978 36.38 29.7678 36.35C35.2178 36.31 42.9378 37.73 49.8878 37.14C51.5978 45.29 57.4878 50.79 62.4378 54.4C59.6278 53.41 50.6278 46.82 45.5578 44.01C37.4878 39.53 29.1778 38.65 24.9278 42.56C21.2678 45.93 21.7778 50.91 22.4578 53.74Z" fill="white"/>
      <path d="M79.8278 64.38V64.35C79.8278 64.35 75.2378 68.72 77.3378 76.65C76.0578 77.89 73.1278 77.42 71.8678 77.23C72.6878 78.27 78.9878 80.57 81.2178 76.78C76.9178 73.45 79.7478 64.95 79.8378 64.39" fill="white"/>
      <path d="M98.1578 23.81C97.8578 25.49 95.9778 26.55 93.9478 26.18C91.9278 25.81 90.5378 24.15 90.8478 22.48C91.1578 20.8 93.0278 19.74 95.0578 20.11C97.0678 20.47 98.4578 22.14 98.1478 23.81" fill="white"/>
      <path d="M89.7478 37.85C81.7478 37.38 75.9378 32.62 74.3078 28.47C73.9378 27.52 74.5178 26.87 75.0778 26.61C75.6478 26.35 76.5978 26.51 76.9578 27.43C79.2078 33.19 83.7778 36.15 89.7478 37.85Z" fill="white"/>
      <path d="M86.9378 44.33C76.0478 44.03 70.1778 39.7 67.1578 33.35C66.8378 32.68 67.0178 31.82 67.8578 31.45C68.6978 31.07 69.4478 31.45 69.7278 32.17C72.5178 39.26 79.9078 43.42 86.9378 44.34" fill="white"/>
      <path d="M59.0178 36.92C63.3078 47.14 72.9078 51.84 84.9078 51.2C73.8278 50.35 65.2978 45.24 61.6478 35.89C61.2978 35.01 60.5778 34.79 59.8978 35C59.2178 35.21 58.6078 35.96 59.0178 36.92Z" fill="white"/>
      <path d="M101.188 24.1901C101.188 24.1901 101.318 28.1301 96.8078 30.1201C92.3378 32.1001 88.4878 29.1701 88.2978 29.0301C88.0178 28.8201 87.8378 28.4801 87.8378 28.1101C87.8378 27.4701 88.3578 26.9601 88.9878 26.9601C89.2778 26.9601 89.5578 27.0701 89.7578 27.2501C89.9678 27.4401 92.4478 29.9601 96.5278 28.9601C100.608 27.9601 101.188 24.1901 101.188 24.1901Z" fill="white"/>
      <path d="M87.7978 21.89C87.7178 22.44 87.2478 22.86 86.6678 22.86C86.0378 22.86 85.5278 22.35 85.5278 21.72C85.5278 21.61 85.5478 21.5 85.5778 21.39C85.6678 21.08 86.7978 17.42 90.9178 16.46C94.9578 15.52 97.6278 17.54 97.6278 17.54C97.6278 17.54 94.6678 15.88 91.2678 17.42C88.4978 18.62 87.8478 21.53 87.7978 21.89Z" fill="white"/>
    </svg>
  );
}
