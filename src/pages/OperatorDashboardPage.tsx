import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  depositInstructions,
  syncDeposits,
  type DepositInstruction
} from "../lib/api";

function parseApiError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  const raw = error.message?.trim();
  if (!raw) return fallback;

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

export default function OperatorDashboardPage() {
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const instructionData = await depositInstructions();
      setInstructions(instructionData);
    } catch (err) {
      setError(parseApiError(err, "Unable to load operator tools right now."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function runDepositSync() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits();
      setMessage(
        `Checked ${result.checked_count} bank activity item(s), matched ${result.matched_count}, and credited ${result.credited_count} deposit(s).`
      );
    } catch (err) {
      setError(parseApiError(err, "Deposit sync failed."));
    } finally {
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
    <div className="ownerDashboard">
      <section className="card ownerHero">
        <div className="ownerHeroEyebrow">Operator tools</div>
        <div className="ownerHeroBalance">BoG sync access</div>
        <p className="ownerHeroNote">
          Use this page for day-to-day payout and funding operations. Admin-only reporting and review pages stay hidden unless your role allows them.
        </p>
        <div className="ownerHeroMeta">
          <span>{instructions?.fleet_name ?? "Active fleet"}</span>
          {loading ? <span>Refreshing...</span> : <span>Operator role</span>}
        </div>
      </section>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Fleet funding instructions</h2>
          <button className="btn btnGhost" type="button" onClick={() => void runDepositSync()}>
            {loading ? "Syncing..." : "Sync from BoG"}
          </button>
        </div>

        {instructions ? (
          <div className="txList" role="list">
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Use this exact fleet reference</div>
                <div className="txSub mappingCode">{instructions.reference_code}</div>
                <div className="txSub">This code must be included in the bank transfer comment so the deposit can be matched.</div>
              </div>
              <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.reference_code)}>
                Copy
              </button>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Company account</div>
                <div className="txSub">{instructions.account_holder_name || "Company account"}</div>
                <div className="txSub">{instructions.account_number}</div>
              </div>
              <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.account_number)}>
                Copy
              </button>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">What happens next</div>
                <div className="txSub">After the next BoG sync, matched funding will be credited to the fleet reserve automatically.</div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="ownerQuickLinks">
        <Link className="card ownerLinkCard" to="/payouts">
          <div className="ownerLinkEyebrow">Payouts</div>
          <div className="txTitle">Track payout progress</div>
          <div className="txSub">Refresh Bank of Georgia payout statuses and follow any in-flight withdrawal requests.</div>
        </Link>
      </section>
    </div>
  );
}
