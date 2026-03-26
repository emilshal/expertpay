import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  depositInstructions,
  depositsList,
  getActiveRole,
  ownerFleetSummary,
  type DepositInstruction,
  type DepositItem,
  type OwnerFleetSummary
} from "../lib/api";

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
  return `${Number(value || 0).toFixed(2)} ${currency}`;
}

function payoutStateLabel(status: string) {
  if (status === "pending") return "Requested";
  if (status === "processing") return "Sending";
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  return status;
}

function buildAlerts(summary: OwnerFleetSummary | null, currency: string) {
  if (!summary) return [];
  const reserve = Number(summary.reserve_balance || 0);
  const pendingTotal = Number(summary.pending_payouts_total || 0);
  const alerts: Array<{ key: string; tone: "danger" | "warn" | "info"; title: string; detail: string; cta: string; to: string }> = [];

  if (reserve <= 0) {
    alerts.push({
      key: "reserve-empty",
      tone: "danger",
      title: "Fleet reserve is empty",
      detail: "Drivers will not be able to withdraw until you add funds to the fleet reserve.",
      cta: "Fund fleet",
      to: "/deposits"
    });
  } else if (summary.pending_payouts_count > 0 && reserve <= pendingTotal) {
    alerts.push({
      key: "reserve-low",
      tone: "warn",
      title: "Fleet reserve is running low",
      detail: `Pending payouts total ${formatMoney(summary.pending_payouts_total, currency)}, which is at or above the current reserve.`,
      cta: "Add funds",
      to: "/deposits"
    });
  }

  if (summary.unmatched_deposits_count > 0) {
    alerts.push({
      key: "deposit-review",
      tone: "warn",
      title: "Incoming deposits need review",
      detail: `${summary.unmatched_deposits_count} bank transfer${summary.unmatched_deposits_count === 1 ? "" : "s"} are waiting to be matched to this fleet.`,
      cta: "Review deposits",
      to: "/deposit-review"
    });
  }

  if (summary.failed_payouts_count > 0) {
    alerts.push({
      key: "failed-payouts",
      tone: "danger",
      title: "Some payouts need attention",
      detail: `${summary.failed_payouts_count} payout${summary.failed_payouts_count === 1 ? "" : "s"} failed for ${formatMoney(summary.failed_payouts_total, currency)}.`,
      cta: "Open payouts",
      to: "/payouts"
    });
  }

  if (summary.pending_payouts_count >= 3) {
    alerts.push({
      key: "pending-payouts",
      tone: "info",
      title: "Payouts are building up",
      detail: `${summary.pending_payouts_count} payouts are still waiting to finish.`,
      cta: "Check status",
      to: "/payouts"
    });
  }

  return alerts;
}

export default function OwnerDashboardPage() {
  const role = getActiveRole();
  const isOwnerAdmin = role === "owner" || role === "admin";
  const [summary, setSummary] = useState<OwnerFleetSummary | null>(null);
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [deposits, setDeposits] = useState<DepositItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [summaryData, instructionData, depositData] = await Promise.all([
        ownerFleetSummary(),
        depositInstructions(),
        depositsList()
      ]);
      setSummary(summaryData);
      setInstructions(instructionData);
      setDeposits(depositData.slice(0, 3));
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const currency = summary?.currency ?? instructions?.currency ?? "GEL";
  const alerts = buildAlerts(summary, currency);

  return (
    <div className="ownerDashboard">
      <section className="card ownerHero">
        <div className="ownerHeroEyebrow">Fleet reserve</div>
        <div className="ownerHeroBalance">
          {formatMoney(summary?.reserve_balance ?? "0.00", currency)}
        </div>
        <p className="ownerHeroNote">
          Fund this reserve to keep driver payouts flowing. Drivers can withdraw only when both earned balance and fleet reserve are available.
        </p>
        <div className="ownerHeroMeta">
          <span>{summary?.fleet_name ?? instructions?.fleet_name ?? "Active fleet"}</span>
          {loading ? <span>Refreshing...</span> : <span>{summary?.active_drivers_count ?? 0} active drivers</span>}
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

      <section className="ownerStatsGrid" aria-label="Fleet overview">
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Total funded</div>
          <div className="ownerStatValue">{formatMoney(summary?.total_funded ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Total withdrawn</div>
          <div className="ownerStatValue">{formatMoney(summary?.total_withdrawn ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Total fees</div>
          <div className="ownerStatValue">{formatMoney(summary?.total_fees ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Pending payouts</div>
          <div className="ownerStatValue">{summary?.pending_payouts_count ?? 0}</div>
          <div className="ownerStatSub">
            {formatMoney(summary?.pending_payouts_total ?? "0.00", currency)}
          </div>
        </article>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Deposit instructions</h2>
          <Link className="btn btnGhost" to="/deposits">
            Open deposits
          </Link>
        </div>

        {instructions ? (
          <div className="txList" role="list">
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Use this exact fleet reference</div>
                <div className="txSub mappingCode">{instructions.reference_code}</div>
                <div className="txSub">Put it in the bank transfer comment so the money can be matched to this fleet.</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Send funds to this company account</div>
                <div className="txSub">{instructions.account_holder_name || "Company account"}</div>
                <div className="txSub">{instructions.account_number}</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">What happens next</div>
                <div className="txSub">Your fleet reserve updates after ExpertPay syncs BoG activity and matches the transfer to this reference.</div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Pending payouts</h2>
          <Link className="btn btnGhost" to="/payouts">
            Open payouts
          </Link>
        </div>

        <div className="txList" role="list">
          {summary?.pending_payouts.length ? (
            summary.pending_payouts.map((item) => (
              <div key={item.id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">{item.driver_name}</div>
                  <div className="txSub">@{item.driver_username}</div>
                  <div className="txSub">{item.created_at}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="txAmount">{formatMoney(item.amount, item.currency)}</div>
                  <div className="txSub">Fleet fee {formatMoney(item.fee_amount, item.currency)}</div>
                  <div className={`ownerPayoutStatus ownerPayoutStatus${item.status}`}>
                    {payoutStateLabel(item.status)}
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">No pending payouts</div>
                <div className="txSub">New withdrawal requests will appear here for quick tracking.</div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Recent funding</h2>
          {isOwnerAdmin ? (
            <Link className="btn btnGhost" to="/deposit-review">
              Review queue
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
                <div className="txSub">Reference {deposit.reference_code}</div>
                <div className="txSub">{deposit.completed_at}</div>
              </div>
              <div className="txAmount pos">Credited</div>
            </div>
          ))
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">No deposits yet</div>
                <div className="txSub">Once transfers are matched to this fleet, funding will show here.</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {isOwnerAdmin ? (
        <section className="ownerQuickLinks">
          <Link className="card ownerLinkCard" to="/fleet-members">
            <div className="ownerLinkEyebrow">Team</div>
            <div className="txTitle">Manage drivers and roles</div>
            <div className="txSub">Update access and keep fleet membership current.</div>
          </Link>
          <Link className="card ownerLinkCard" to="/deposits">
            <div className="ownerLinkEyebrow">Funding</div>
            <div className="txTitle">Fund fleet reserve</div>
            <div className="txSub">Use your fleet reference and confirm recent funding landed as expected.</div>
          </Link>
          <Link className="card ownerLinkCard" to="/payouts">
            <div className="ownerLinkEyebrow">Payouts</div>
            <div className="txTitle">Track payout progress</div>
            <div className="txSub">Review payout states, destinations, and any failures that need action.</div>
          </Link>
        </section>
      ) : null}

      {isOwnerAdmin ? (
        <section className="ownerInternalTools">
          <div className="cardTitleRow">
            <h2 className="h2">Internal tools</h2>
            <div className="txSub">Open these only when you need review, diagnostics, or mapping fixes.</div>
          </div>

          <div className="ownerQuickLinks">
            <Link className="card ownerLinkCard" to="/deposit-review">
              <div className="ownerLinkEyebrow">Deposit review</div>
              <div className="txTitle">Match incoming transfers</div>
              <div className="txSub">Resolve unmatched bank transfers and backfill missed funding when needed.</div>
            </Link>
            <Link className="card ownerLinkCard" to="/driver-mappings">
              <div className="ownerLinkEyebrow">Driver mappings</div>
              <div className="txTitle">Review Yandex driver links</div>
              <div className="txSub">Keep fleet earnings attached to the correct driver accounts.</div>
            </Link>
            <Link className="card ownerLinkCard" to="/connect-yandex">
              <div className="ownerLinkEyebrow">Yandex</div>
              <div className="txTitle">Open Yandex operations</div>
              <div className="txSub">Refresh the connection, run syncs, or inspect raw import data only when needed.</div>
            </Link>
            <Link className="card ownerLinkCard" to="/settings">
              <div className="ownerLinkEyebrow">Reconciliation</div>
              <div className="txTitle">Check treasury health</div>
              <div className="txSub">Open the diagnostics view when balances or payout states need deeper review.</div>
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}
