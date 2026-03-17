import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  depositInstructions,
  depositsList,
  syncDeposits,
  type DepositInstruction,
  type DepositItem
} from "../lib/api";

export default function DepositsPage() {
  const navigate = useNavigate();
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [deposits, setDeposits] = useState<DepositItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [instructionData, depositData] = await Promise.all([depositInstructions(), depositsList()]);
      setInstructions(instructionData);
      setDeposits(depositData);
    } catch {
      setError("Unable to load deposit details right now.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function runSync() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits();
      setMessage(
        `Checked ${result.checked_count} bank activity item(s), matched ${result.matched_count}, credited ${result.credited_count} for ${result.credited_total} GEL.`
      );
      await loadData();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "Deposit sync failed.");
      setLoading(false);
    }
  }

  async function copyValue(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage("Copied.");
    } catch {
      setMessage("Copy failed.");
    }
  }

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>Deposits</h1>
        <div className="toolbarRow">
          <button className="btn btnGhost" type="button" onClick={() => navigate("/card-topup")}>
            Card top-up
          </button>
          <button className="btn btnGhost" type="button" onClick={() => navigate("/deposit-review")}>
            Review Queue
          </button>
          <button className="btn btnGhost" type="button" onClick={() => void runSync()}>
            {loading ? "Syncing..." : "Sync from BoG"}
          </button>
        </div>
      </div>

      <p className="muted">Send a bank transfer to your company account, or use card top-up through BoG checkout.</p>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      {instructions ? (
        <div className="txList" role="list" style={{ marginTop: "14px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Bank</div>
              <div className="txSub">{instructions.bank_name}</div>
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Account holder</div>
              <div className="txSub">{instructions.account_holder_name || "Company account"}</div>
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Account number</div>
              <div className="txSub">{instructions.account_number}</div>
            </div>
            <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.account_number)}>
              Copy
            </button>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Reference code</div>
              <div className="txSub">{instructions.reference_code}</div>
            </div>
            <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.reference_code)}>
              Copy
            </button>
          </div>
        </div>
      ) : null}

      <h2 className="h2" style={{ marginTop: "22px", marginBottom: "10px" }}>
        Recent deposits
      </h2>
      <div className="txList" role="list">
        {deposits.length ? (
          deposits.map((deposit) => (
            <div key={deposit.id} className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">
                  {deposit.amount} {deposit.currency}
                </div>
                <div className="txSub">{deposit.payer_name || deposit.reference_code}</div>
                <div className="txSub">{deposit.completed_at}</div>
              </div>
              <div className="txAmount pos">{deposit.status}</div>
            </div>
          ))
        ) : (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No deposits yet</div>
              <div className="txSub">Once incoming transfers are matched, they will show here.</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
