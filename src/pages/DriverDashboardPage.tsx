import { useEffect, useMemo, useState } from "react";
import {
  bankAccounts,
  createBankAccount,
  createWithdrawal,
  walletBalance,
  withdrawalsList,
  type BankAccount,
  type WithdrawalItem
} from "../lib/api";

function formatApiError(error: unknown) {
  if (!(error instanceof Error)) return "Request failed.";
  const raw = error.message?.trim();
  if (!raw) return "Request failed.";

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

function friendlyWithdrawalError(error: unknown) {
  const message = formatApiError(error);
  if (message.includes("Insufficient driver available balance")) {
    return "You do not have enough withdrawable earnings for this request yet.";
  }
  if (message.includes("Insufficient fleet reserve balance")) {
    return "Your fleet does not have enough reserve funding right now. Please ask your fleet owner to top up the reserve.";
  }
  if (message.includes("Bank account not found")) {
    return "Choose a saved bank account before requesting a payout.";
  }
  return message;
}

function withdrawalStatusLabel(status: WithdrawalItem["status"]) {
  if (status === "pending") return "Requested";
  if (status === "processing") return "Processing";
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  return status;
}

function withdrawalStatusHint(item: WithdrawalItem) {
  if (item.status === "pending") return "Your request was received and is waiting to be sent.";
  if (item.status === "processing") return "Your payout is being sent through Bank of Georgia.";
  if (item.status === "completed") return "The payout finished successfully.";
  if (item.status === "failed") return "This payout did not complete. Any held balance should be returned automatically.";
  return "";
}

function formatDateTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

export default function DriverDashboardPage() {
  const [balance, setBalance] = useState("0.00");
  const [currency, setCurrency] = useState("GEL");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [selectedBankAccountId, setSelectedBankAccountId] = useState<number | null>(null);

  const [bankName, setBankName] = useState("Bank of Georgia");
  const [accountNumber, setAccountNumber] = useState("");
  const [beneficiaryName, setBeneficiaryName] = useState("");
  const [beneficiaryInn, setBeneficiaryInn] = useState("");
  const [savingBank, setSavingBank] = useState(false);
  const [submittingWithdrawal, setSubmittingWithdrawal] = useState(false);

  const selectedAccount = useMemo(
    () => accounts.find((item) => item.id === selectedBankAccountId) ?? accounts[0] ?? null,
    [accounts, selectedBankAccountId]
  );
  const numericBalance = Number(balance || 0);
  const numericAmount = Number(amount || 0);
  const hasPositiveAmount = Number.isFinite(numericAmount) && numericAmount > 0;
  const amountExceedsAvailable = hasPositiveAmount && numericAmount > numericBalance;
  const hasBankAccount = Boolean(selectedAccount);
  const withdrawalBlockedReason = !hasBankAccount
    ? "Add a bank account before requesting a payout."
    : !amount
      ? "Enter the amount you want to receive."
      : !hasPositiveAmount
        ? "Enter an amount greater than 0.00."
        : amountExceedsAvailable
          ? "This amount is higher than your current withdrawable balance."
          : "";
  const canSubmitWithdrawal = !submittingWithdrawal && !withdrawalBlockedReason;

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [balanceData, accountData, withdrawalData] = await Promise.all([
        walletBalance(),
        bankAccounts(),
        withdrawalsList()
      ]);
      setBalance(balanceData.balance);
      setCurrency(balanceData.currency);
      setAccounts(accountData);
      setWithdrawals(withdrawalData);
      setSelectedBankAccountId((current) => current ?? accountData[0]?.id ?? null);
    } catch (err) {
      setError(friendlyWithdrawalError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleAddBankAccount() {
    setSavingBank(true);
    setError("");
    setMessage("");
    try {
      const account = await createBankAccount({
        bank_name: bankName,
        account_number: accountNumber,
        beneficiary_name: beneficiaryName,
        beneficiary_inn: beneficiaryInn
      });
      setAccounts((prev) => [account, ...prev]);
      setSelectedBankAccountId(account.id);
      setAccountNumber("");
      setBeneficiaryName("");
      setBeneficiaryInn("");
      setMessage("Bank account saved. You can use it for your next payout.");
    } catch (err) {
      setError(friendlyWithdrawalError(err));
    } finally {
      setSavingBank(false);
    }
  }

  async function handleWithdraw() {
    if (!selectedAccount) {
      setError("Add a bank account before requesting a payout.");
      return;
    }

    setSubmittingWithdrawal(true);
    setError("");
    setMessage("");
    try {
      const withdrawal = await createWithdrawal({
        bank_account_id: selectedAccount.id,
        amount,
        note
      });
      setWithdrawals((prev) => [withdrawal, ...prev]);
      setAmount("");
      setNote("");
      await loadData();
      setMessage("Payout requested. We’ll show it as requested first, then processing while Bank of Georgia sends it.");
    } catch (err) {
      setError(friendlyWithdrawalError(err));
    } finally {
      setSubmittingWithdrawal(false);
    }
  }

  return (
    <div className="driverDashboard">
      <section className="card driverHero">
        <div className="driverHeroEyebrow">Available to withdraw</div>
        <div className="driverHeroBalance">
          {Number(balance || 0).toFixed(2)} {currency}
        </div>
        <p className="driverHeroNote">This is the amount you can request from your synced earnings. Payouts are sent only when your fleet reserve can also cover them.</p>
        {!numericBalance ? <p className="statusHint">No withdrawable earnings are available right now.</p> : null}
        {loading ? <p className="statusHint">Refreshing your balance...</p> : null}
      </section>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Withdraw</h2>
        </div>
        <p className="muted">Request a payout to your saved bank account. Your fleet covers the withdrawal fee, so the fee is not deducted from your earnings.</p>
        <div className="transferForm">
          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input
              className="transferInput"
              type="number"
              min="0"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>

          <label className="transferField">
            <span className="transferLabel">Bank account</span>
            <select
              className="transferInput"
              value={selectedAccount?.id ?? ""}
              onChange={(event) => setSelectedBankAccountId(Number(event.target.value))}
            >
              {accounts.length ? null : <option value="">No saved account yet</option>}
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.bank_name} • {account.account_number}
                </option>
              ))}
            </select>
          </label>

          <label className="transferField">
            <span className="transferLabel">Note</span>
            <input
              className="transferInput"
              type="text"
              placeholder="Optional note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>

          <button className="transferSubmit" type="button" disabled={!canSubmitWithdrawal} onClick={() => void handleWithdraw()}>
            {submittingWithdrawal ? "Requesting..." : "Request payout"}
          </button>
        </div>
        {withdrawalBlockedReason ? <p className="statusHint">{withdrawalBlockedReason}</p> : null}
        {hasBankAccount && hasPositiveAmount && !amountExceedsAvailable ? (
          <p className="statusHint">If your fleet reserve is too low, we’ll explain that after you submit the request.</p>
        ) : null}
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Saved bank account</h2>
        </div>
        {selectedAccount ? (
          <div className="driverBankSummary">
            <div className="txTitle">{selectedAccount.bank_name}</div>
            <div className="txSub">{selectedAccount.account_number}</div>
            <div className="txSub">{selectedAccount.beneficiary_name}</div>
            <div className="txSub">ID number {selectedAccount.beneficiary_inn}</div>
          </div>
        ) : (
          <p className="muted">No bank account saved yet. Add one below before you request your first payout.</p>
        )}

        <div className="transferForm" style={{ marginTop: 16 }}>
          <label className="transferField">
            <span className="transferLabel">Bank name</span>
            <input className="transferInput" value={bankName} onChange={(event) => setBankName(event.target.value)} />
          </label>
          <label className="transferField">
            <span className="transferLabel">Account number</span>
            <input
              className="transferInput"
              value={accountNumber}
              placeholder="GE..."
              onChange={(event) => setAccountNumber(event.target.value)}
            />
          </label>
          <label className="transferField">
            <span className="transferLabel">Beneficiary name</span>
            <input
              className="transferInput"
              value={beneficiaryName}
              onChange={(event) => setBeneficiaryName(event.target.value)}
            />
          </label>
          <label className="transferField">
            <span className="transferLabel">Beneficiary INN</span>
            <input
              className="transferInput"
              value={beneficiaryInn}
              onChange={(event) => setBeneficiaryInn(event.target.value)}
            />
          </label>
          <button className="btn btnGhost" type="button" disabled={savingBank} onClick={() => void handleAddBankAccount()}>
            {savingBank ? "Saving..." : "Save bank account"}
          </button>
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Payout history</h2>
          <button className="btn btnGhost" type="button" onClick={() => void loadData()}>
            Refresh
          </button>
        </div>
        <div className="txList" role="list">
          {withdrawals.length ? (
            withdrawals.map((item) => (
              <div key={item.id} className="txRow" role="listitem">
                <div className="txMain">
                <div className="txTitle">
                  {Number(item.amount).toFixed(2)} {item.currency}
                </div>
                  <div className="txSub">To {item.bank_account.bank_name} • {item.bank_account.account_number}</div>
                  <div className="txSub">Fleet fee paid {Number(item.fee_amount || 0).toFixed(2)} {item.currency}</div>
                  {item.note ? <div className="txSub">{item.note}</div> : null}
                  <div className="txSub">{formatDateTime(item.created_at)}</div>
                  <div className="txSub">{withdrawalStatusHint(item)}</div>
                </div>
                <div className={`txAmount ${item.status === "completed" ? "pos" : item.status === "failed" ? "neg" : ""}`}>
                  {withdrawalStatusLabel(item.status)}
                </div>
              </div>
            ))
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">No payouts yet</div>
                <div className="txSub">Your requested, processing, completed, and failed payouts will appear here.</div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
