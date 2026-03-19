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
                <div className="txTitle">Reference code</div>
                <div className="txSub">{instructions.reference_code}</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Bank account</div>
                <div className="txSub">{instructions.account_holder_name || "Company account"}</div>
                <div className="txSub">{instructions.account_number}</div>
              </div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Funding note</div>
                <div className="txSub">{instructions.note}</div>
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
                  <div className="txSub">Fee {formatMoney(item.fee_amount, item.currency)}</div>
                  <div className={`ownerPayoutStatus ownerPayoutStatus${item.status}`}>
                    {item.status}
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
                  <div className="txSub">{deposit.completed_at}</div>
                </div>
                <div className="txAmount pos">{deposit.status}</div>
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
          <Link className="card ownerLinkCard" to="/driver-mappings">
            <div className="ownerLinkEyebrow">Mappings</div>
            <div className="txTitle">Review Yandex driver links</div>
            <div className="txSub">Keep fleet earnings attached to the correct driver accounts.</div>
          </Link>
          <Link className="card ownerLinkCard" to="/settings">
            <div className="ownerLinkEyebrow">Reconciliation</div>
            <div className="txTitle">Check treasury health</div>
            <div className="txSub">Use ops pages only when you need deeper diagnostics.</div>
          </Link>
        </section>
      ) : null}
    </div>
  );
}
