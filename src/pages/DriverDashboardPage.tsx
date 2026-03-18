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
      setError(formatApiError(err));
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
      setMessage("Bank account saved.");
    } catch (err) {
      setError(formatApiError(err));
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
      setMessage("Withdrawal request submitted.");
    } catch (err) {
      setError(formatApiError(err));
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
        <p className="driverHeroNote">Your balance is based on synced earnings and your fleet’s available reserve.</p>
        {loading ? <p className="statusHint">Refreshing your balance...</p> : null}
      </section>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Withdraw</h2>
        </div>
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

          <button className="transferSubmit" type="button" disabled={submittingWithdrawal} onClick={() => void handleWithdraw()}>
            {submittingWithdrawal ? "Submitting..." : "Withdraw"}
          </button>
        </div>
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
          </div>
        ) : (
          <p className="muted">No bank account saved yet.</p>
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
                  <div className="txSub">{item.bank_account.bank_name}</div>
                  <div className="txSub">{item.created_at}</div>
                </div>
                <div className={`txAmount ${item.status === "completed" ? "pos" : ""}`}>{item.status}</div>
              </div>
            ))
          ) : (
            <p className="muted">No payout history yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
