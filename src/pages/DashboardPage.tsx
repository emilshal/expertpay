import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  bankAccounts,
  createBankAccount,
  createInternalTransferByBank,
  createWithdrawal,
  topUpWallet,
  walletBalance,
  walletTransactions,
  type BankAccount,
  type TransactionFeedItem
} from "../lib/api";

function formatApiError(
  error: unknown,
  fieldLabels: Record<string, string> = {}
) {
  const fallback = "Request failed.";
  if (!(error instanceof Error)) return fallback;

  const raw = error.message?.trim();
  if (!raw) return fallback;

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;

    const parts: string[] = [];
    for (const [key, value] of Object.entries(parsed)) {
      const label = fieldLabels[key] ?? key.replace(/_/g, " ");
      if (Array.isArray(value) && value.length) {
        parts.push(`${label}: ${String(value[0])}`);
      } else if (typeof value === "string") {
        parts.push(`${label}: ${value}`);
      }
    }

    return parts.join(" | ") || raw;
  } catch {
    return raw;
  }
}

export default function DashboardPage() {
  const [isBonusesOpen, setBonusesOpen] = useState(false);
  const [isTransferOpen, setTransferOpen] = useState(false);
  const [isWithdrawOpen, setWithdrawOpen] = useState(false);
  const [isTopUpOpen, setTopUpOpen] = useState(false);
  const [isRentOpen, setRentOpen] = useState(false);

  const [balance, setBalance] = useState("0.00");
  const [currency, setCurrency] = useState("GEL");
  const [transactions, setTransactions] = useState<TransactionFeedItem[]>([]);
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [loadingData, setLoadingData] = useState(false);
  const [dataError, setDataError] = useState("");

  async function loadAppData() {
    setLoadingData(true);
    setDataError("");
    try {
      const [balanceRes, txRes, bankRes] = await Promise.all([walletBalance(), walletTransactions(), bankAccounts()]);
      setBalance(balanceRes.balance);
      setCurrency(balanceRes.currency);
      setTransactions(txRes);
      setAccounts(bankRes);
    } catch {
      setDataError("Unable to load data from backend.");
    } finally {
      setLoadingData(false);
    }
  }

  useEffect(() => {
    void loadAppData();
  }, []);

  const formattedBalance = Number(balance || 0).toFixed(2);

  return (
    <div className="dashboard">
      <div className="dashboardQuickRow">
        <IconButton label="Referrals" variant="ghost" icon={<IconReferral />} />
        <IconButton
          label="Bonuses"
          variant="ghost"
          icon={<IconGift />}
          onClick={() => setBonusesOpen(true)}
        />
        <IconButton label="Renting" variant="ghost" icon={<IconCar />} onClick={() => setRentOpen(true)} />
      </div>

      <section className="card balanceCard">
        <div className="balanceHeader">
          <div>
            <div className="muted">Your balance</div>
            <div className="balanceValue">
              {formattedBalance} {currency}
            </div>
          </div>
          {loadingData ? <div className="muted">Syncing...</div> : null}
        </div>
      </section>

      <section className="card cardTransparent">
        <div className="actionRow" aria-label="Actions">
          <IconButton
            label="Withdraw money"
            variant="soft"
            icon={<IconSend />}
            onClick={() => setWithdrawOpen(true)}
          />
          <IconButton
            label="Transfer to someone"
            variant="soft"
            icon={<IconUsers />}
            onClick={() => setTransferOpen(true)}
          />
          <IconButton
            label="Fill up balance"
            variant="soft"
            icon={<IconPlus />}
            onClick={() => setTopUpOpen(true)}
          />
          <IconButton label="Video tariffs" variant="soft" icon={<IconPlay />} />
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Transaction history</h2>
          <button className="btn btnGhost" type="button" onClick={() => void loadAppData()}>
            Refresh
          </button>
        </div>

        {dataError ? <p className="statusError">{dataError}</p> : null}

        <div className="txList" role="list">
          {transactions.map((tx) => (
            <TransactionRow key={tx.id} tx={tx} />
          ))}
          {!transactions.length ? <p className="muted">No transactions yet.</p> : null}
        </div>
      </section>

      {isBonusesOpen ? <BonusesModal onClose={() => setBonusesOpen(false)} /> : null}
      {isTransferOpen ? <TransferModal onClose={() => setTransferOpen(false)} onSuccess={loadAppData} /> : null}
      {isWithdrawOpen ? (
        <WithdrawModal
          onClose={() => setWithdrawOpen(false)}
          onSuccess={loadAppData}
          bankAccounts={accounts}
          setBankAccounts={setAccounts}
        />
      ) : null}
      {isTopUpOpen ? <TopUpModal onClose={() => setTopUpOpen(false)} onSuccess={loadAppData} /> : null}
      {isRentOpen ? <RentModal onClose={() => setRentOpen(false)} /> : null}
    </div>
  );
}

function TransactionRow({ tx }: { tx: TransactionFeedItem }) {
  const amountNum = Number(tx.amount);
  const positive = amountNum > 0;
  const title = useMemo(() => {
    if (tx.kind === "withdrawal") return "Withdrawal";
    if (tx.kind === "internal_transfer") return "Internal transfer";
    return "Adjustment";
  }, [tx.kind]);

  return (
    <div className="txRow" role="listitem">
      <div className="txMain">
        <div className="txTitle">{tx.description || title}</div>
        <div className="txSub">{tx.status}</div>
      </div>
      <div className={`txAmount ${positive ? "pos" : "neg"}`}>
        {positive ? "+" : "-"}
        {Math.abs(amountNum).toFixed(2)} {tx.currency}
      </div>
    </div>
  );
}

function IconButton({
  label,
  icon,
  variant = "soft",
  onClick
}: {
  label: string;
  icon: ReactNode;
  variant?: "ghost" | "soft";
  onClick?: () => void;
}) {
  const className = variant === "ghost" ? "iconBtn btnGhost" : "iconBtn btnSoft";
  return (
    <button className={className} type="button" aria-label={label} onClick={onClick}>
      <span className="iconBtnIcon" aria-hidden="true">
        {icon}
      </span>
      <span className="iconBtnLabel">{label}</span>
    </button>
  );
}

function BonusesModal({ onClose }: { onClose: () => void }) {
  const items = [
    { title: "Top Driver", icon: <IconMedal />, unread: true },
    { title: "Formula 1 Pro", icon: <IconFlag /> },
    { title: "Fuel", icon: <IconFuel /> },
    { title: "Referrals", icon: <IconReferralGroup /> },
    { title: "Cashback", icon: <IconMoneyBag /> },
    { title: "Star bonus", icon: <IconSpark />, muted: true }
  ];

  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="bonusModal"
        role="dialog"
        aria-modal="true"
        aria-label="Your bonuses"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close bonuses" onClick={onClose}>
          <IconClose />
        </button>

        <div className="bonusHeader">
          <span className="bonusTrophy" aria-hidden="true">
            <IconTrophy />
          </span>
          <h2 className="bonusTitle">Your bonuses</h2>
          <p className="bonusAmount">Total bonus given to drivers: 96,700.78 GEL</p>
          <p className="bonusAmount bonusAmountSecondary">You received: 0.00 GEL</p>
        </div>

        <div className="bonusGrid" role="list">
          {items.map((item) => (
            <button
              key={item.title}
              className={`bonusTile ${item.muted ? "bonusTileMuted" : ""}`}
              type="button"
              role="listitem"
            >
              {item.unread ? <span className="bonusBadge">1</span> : null}
              <span className="bonusTileIcon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="bonusTileLabel">{item.title}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function TransferModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => Promise<void> }) {
  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [beneficiaryName, setBeneficiaryName] = useState("");
  const [amount, setAmount] = useState("0.1489");
  const [note, setNote] = useState("Private transfer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setLoading(true);
    setError("");
    try {
      await createInternalTransferByBank({
        bank_name: bankName,
        account_number: accountNumber,
        beneficiary_name: beneficiaryName,
        amount,
        note
      });
      await onSuccess();
      onClose();
    } catch (err) {
      setError(
        formatApiError(err, {
          bank_name: "Choose bank",
          account_number: "Account number",
          beneficiary_name: "Beneficiary name",
          amount: "Amount",
          note: "Nomination"
        })
      );
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
        aria-label="Transfer to someone"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close transfer" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="transferTitle">Transfer</h2>

        <form className="transferForm" onSubmit={(event) => event.preventDefault()}>
          <label className="transferField">
            <span className="transferLabel">Choose bank</span>
            <CustomDropdown
              value={bankName}
              placeholder="Select bank"
              options={[
                { value: "TBC", label: "TBC" },
                { value: "Bank of Georgia", label: "Bank of Georgia" }
              ]}
              onChange={(value) => setBankName(value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Account number</span>
            <input
              className="transferInput"
              type="text"
              value={accountNumber}
              onChange={(event) => setAccountNumber(event.target.value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Beneficiary name</span>
            <input
              className="transferInput"
              type="text"
              value={beneficiaryName}
              onChange={(event) => setBeneficiaryName(event.target.value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input
              className="transferInput"
              type="text"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Nomination</span>
            <input
              className="transferInput"
              type="text"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>

          <button className="transferSubmit" type="button" onClick={() => void submit()}>
            {loading ? "Please wait..." : "Transfer"}
          </button>
          {error ? <p className="statusError">{error}</p> : null}
        </form>
      </section>
    </div>
  );
}

function WithdrawModal({
  onClose,
  onSuccess,
  bankAccounts,
  setBankAccounts
}: {
  onClose: () => void;
  onSuccess: () => Promise<void>;
  bankAccounts: BankAccount[];
  setBankAccounts: (value: BankAccount[]) => void;
}) {
  const [selectedBankAccountId, setSelectedBankAccountId] = useState<number | "new">(
    bankAccounts[0]?.id ?? "new"
  );
  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [beneficiaryName, setBeneficiaryName] = useState("");
  const [beneficiaryInn, setBeneficiaryInn] = useState("");
  const [amount, setAmount] = useState("0.00");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bankAccountOptions = bankAccounts.map((item) => ({
    value: String(item.id),
    label: `${item.bank_name} • ${item.account_number}`
  }));

  async function submit() {
    setLoading(true);
    setError("");
    try {
      let bankId: number;
      if (selectedBankAccountId === "new") {
        const newAccount = await createBankAccount({
          bank_name: bankName,
          account_number: accountNumber,
          beneficiary_name: beneficiaryName,
          beneficiary_inn: beneficiaryInn
        });
        bankId = newAccount.id;
        setBankAccounts([newAccount, ...bankAccounts]);
      } else {
        bankId = selectedBankAccountId;
      }

      await createWithdrawal({ bank_account_id: bankId, amount });
      await onSuccess();
      onClose();
    } catch (err) {
      setError(
        formatApiError(err, {
          bank_name: "Bank name",
          account_number: "Account number",
          beneficiary_name: "Beneficiary name",
          beneficiary_inn: "Beneficiary ID number",
          bank_account_id: "Bank account",
          amount: "Amount",
          note: "Note"
        })
      );
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
        aria-label="Withdraw"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close withdraw" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="transferTitle">Withdraw</h2>

        <form className="transferForm" onSubmit={(event) => event.preventDefault()}>
          <label className="transferField">
            <span className="transferLabel">Choose bank account</span>
            <CustomDropdown
              value={String(selectedBankAccountId)}
              options={[...bankAccountOptions, { value: "new", label: "Add new bank account" }]}
              onChange={(value) => setSelectedBankAccountId(value === "new" ? "new" : Number(value))}
            />
          </label>

          {selectedBankAccountId === "new" ? (
            <>
              <label className="transferField">
                <span className="transferLabel">Bank name</span>
                <CustomDropdown
                  value={bankName}
                  placeholder="Select bank"
                  options={[
                    { value: "TBC", label: "TBC" },
                    { value: "Bank of Georgia", label: "Bank of Georgia" }
                  ]}
                  onChange={(value) => setBankName(value)}
                />
              </label>

              <label className="transferField">
                <span className="transferLabel">Account number</span>
                <input
                  className="transferInput"
                  type="text"
                  inputMode="numeric"
                  placeholder="GE00 TB00 0000"
                  value={accountNumber}
                  onChange={(event) => setAccountNumber(event.target.value)}
                />
              </label>

              <label className="transferField">
                <span className="transferLabel">Beneficiary name</span>
                <input
                  className="transferInput"
                  type="text"
                  placeholder="Full name"
                  value={beneficiaryName}
                  onChange={(event) => setBeneficiaryName(event.target.value)}
                />
              </label>

              <label className="transferField">
                <span className="transferLabel">Beneficiary ID number</span>
                <input
                  className="transferInput"
                  type="text"
                  inputMode="numeric"
                  placeholder="Personal or company ID"
                  value={beneficiaryInn}
                  onChange={(event) => setBeneficiaryInn(event.target.value)}
                />
              </label>
            </>
          ) : null}

          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input
              className="transferInput"
              type="text"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>

          <button className="transferSubmit" type="button" onClick={() => void submit()}>
            {loading ? "Please wait..." : "Withdrawal"}
          </button>
          {error ? <p className="statusError">{error}</p> : null}
        </form>
      </section>
    </div>
  );
}

function RentModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="rentModal"
        role="dialog"
        aria-modal="true"
        aria-label="Rent a car"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close rent modal" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="rentTitle">Rent a car</h2>
        <p className="rentCopy">
          Taxio is a platform where you can quickly and easily rent the car you want to work as a
          taxi.
        </p>

        <a className="transferSubmit rentSubmit" href="https://taxio.ge/" target="_blank" rel="noreferrer">
          View cars
        </a>
      </section>
    </div>
  );
}

function TopUpModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => Promise<void> }) {
  const [amount, setAmount] = useState("50.00");
  const [note, setNote] = useState("Sandbox top-up");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setLoading(true);
    setError("");
    try {
      await topUpWallet({ amount, note });
      await onSuccess();
      onClose();
    } catch {
      setError("Top-up failed. Check amount.");
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
        aria-label="Fill up balance"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close top-up" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="transferTitle">Fill up balance</h2>

        <form className="transferForm" onSubmit={(event) => event.preventDefault()}>
          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input
              className="transferInput"
              type="text"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Note</span>
            <input
              className="transferInput"
              type="text"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>

          <button className="transferSubmit" type="button" onClick={() => void submit()}>
            {loading ? "Please wait..." : "Top up"}
          </button>
          {error ? <p className="statusError">{error}</p> : null}
        </form>
      </section>
    </div>
  );
}

function CustomDropdown({
  value,
  options,
  onChange,
  placeholder = "Select"
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const selected = options.find((item) => item.value === value);

  useEffect(() => {
    function handleOutside(event: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  return (
    <div className="customSelect" ref={rootRef}>
      <button
        className="transferInput customSelectButton"
        type="button"
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{selected?.label ?? placeholder}</span>
        <span className="transferChevron customSelectChevron" aria-hidden="true">
          <IconChevronDown />
        </span>
      </button>

      {open ? (
        <div className="customSelectMenu" role="listbox">
          {options.map((item) => (
            <button
              key={item.value}
              className={`customSelectOption ${item.value === value ? "customSelectOptionActive" : ""}`}
              type="button"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onChange(item.value);
                setOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4 12L20 4l-4 16-4.5-6L4 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M20 4 11.5 14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconUsers() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M16 11a3 3 0 1 0-2.999-3A3 3 0 0 0 16 11Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M8.5 12a2.5 2.5 0 1 0-2.5-2.5A2.5 2.5 0 0 0 8.5 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M12.5 20c.3-2.7 2.6-5 5.5-5s5.2 2.3 5.5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M1 20c.2-2.2 2.1-4 4.5-4 1.2 0 2.3.4 3.1 1.1"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconPlay() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4.5 8.5A2.5 2.5 0 0 1 7 6h7a2.5 2.5 0 0 1 2.5 2.5V9l2.9-1.9c.8-.5 1.8.1 1.8 1v7.8c0 .9-1 1.5-1.8 1L16.5 15v.5A2.5 2.5 0 0 1 14 18H7a2.5 2.5 0 0 1-2.5-2.5v-7Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="10.5" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M9 6V4.8a.8.8 0 0 1 .8-.8h1.4a.8.8 0 0 1 .8.8V6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconGift() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M20 12v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M4 12h16V8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v4Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M12 6v16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M12 6c-1.6 0-3-1.2-3-2.5S10.4 1 12 3c1.6-2 3-1.5 3 .5S13.6 6 12 6Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconCar() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4.8 12.8 8 8.5c.4-.6 1.1-.9 1.8-.9h4.4c.7 0 1.4.3 1.8.9l3.2 4.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M5.2 12.7h13.6a1.8 1.8 0 0 1 1.8 1.8v2.1H3.4v-2.1a1.8 1.8 0 0 1 1.8-1.8Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M6.6 16.6v1.8M17.4 16.6v1.8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="8.2" cy="14.8" r="1.1" fill="currentColor" />
      <circle cx="15.8" cy="14.8" r="1.1" fill="currentColor" />
      <path d="M9.8 10.6h4.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function IconReferral() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M10.5 13a3.5 3.5 0 1 1 0-5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M13.5 11a3.5 3.5 0 1 1 0 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M9.8 12h4.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
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

function IconTrophy() {
  return (
    <svg viewBox="0 0 24 24" width="30" height="30" fill="none" aria-hidden="true">
      <path
        d="M7 4h10v2a5 5 0 0 1-10 0V4ZM12 11v3M9 20h6M10 14h4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M17 6h2a2 2 0 0 1-2 2M7 6H5a2 2 0 0 0 2 2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconMedal() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M10 4h4l-1.3 4h-1.4L10 4Z" fill="currentColor" />
      <path d="m10 16-1 4 3-1.5L15 20l-1-4" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function IconFlag() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path d="M7 4v16M7 6h10l-2.2 2L17 10H7" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function IconFuel() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="M7 6h7v12H7V6Zm7 2h2l1.5 2.2V16a1.5 1.5 0 1 0 3 0v-5l-2-2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconReferralGroup() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <circle cx="12" cy="9" r="2.8" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.2 18c.8-2 2.8-3.2 5-3.2s4.2 1.2 5 3.2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="6.5" cy="10.4" r="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17.5" cy="10.4" r="2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function IconMoneyBag() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="M12 6c4 0 6.5 3 6.5 6.3A6.5 6.5 0 0 1 12 19a6.5 6.5 0 0 1-6.5-6.7C5.5 9 8 6 12 6Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path d="M10 4h4l-1.2 2.2h-1.6L10 4Z" fill="currentColor" />
      <path d="M12 9v6M10 11.2c0-1 4-1 4 0s-4 1-4 2 4 1 4 0" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function IconSpark() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="m12 3 2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2L12 3Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconChevronDown() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true">
      <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}
