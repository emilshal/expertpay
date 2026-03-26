import { useEffect, useState } from "react";
import { platformEarningsSummary, type PlatformEarningsSummary } from "../lib/api";

function formatMoney(value: string, currency: string) {
  return `${Number(value || 0).toFixed(2)} ${currency}`;
}

function formatApiError(error: unknown) {
  if (!(error instanceof Error)) return "Unable to load platform earnings.";
  const raw = error.message?.trim();
  if (!raw) return "Unable to load platform earnings.";

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

export default function PlatformEarningsPage() {
  const [summary, setSummary] = useState<PlatformEarningsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const payload = await platformEarningsSummary();
      setSummary(payload);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const currency = summary?.currency ?? "GEL";

  return (
    <div className="ownerDashboard">
      <section className="card ownerHero platformHero">
        <div className="ownerHeroEyebrow">Internal only</div>
        <div className="ownerHeroBalance">
          {formatMoney(summary?.total_fees_earned ?? "0.00", currency)}
        </div>
        <p className="ownerHeroNote">
          Platform fee revenue across all fleets. This page is visible only to the ExpertPay internal team.
        </p>
        <div className="ownerHeroMeta">
          <span>Platform earnings</span>
          <span>{loading ? "Refreshing..." : `${summary?.fees_by_fleet.length ?? 0} fleets with fees`}</span>
        </div>
      </section>

      {error ? <p className="statusError">{error}</p> : null}

      <section className="ownerStatsGrid" aria-label="Platform earnings overview">
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Total fees earned</div>
          <div className="ownerStatValue">{formatMoney(summary?.total_fees_earned ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Last 7 days</div>
          <div className="ownerStatValue">{formatMoney(summary?.recent_totals.last_7_days ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">Last 30 days</div>
          <div className="ownerStatValue">{formatMoney(summary?.recent_totals.last_30_days ?? "0.00", currency)}</div>
        </article>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Fees by fleet</h2>
        </div>

        {summary?.fees_by_fleet.length ? (
          <div className="txList" role="list">
            {summary.fees_by_fleet.map((fleet) => (
              <div key={fleet.fleet_id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">{fleet.fleet_name}</div>
                  <div className="txSub">Platform fee revenue from this fleet</div>
                </div>
                <div className="txMeta">
                  <div className="txAmount">{formatMoney(fleet.total_fees_earned, currency)}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="statusHint">No platform fees have been recorded yet.</p>
        )}
      </section>
    </div>
  );
}
