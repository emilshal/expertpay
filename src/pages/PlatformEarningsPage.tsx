import { useEffect, useState } from "react";
import { platformEarningsSummary, type PlatformEarningsSummary } from "../lib/api";
import { useI18n } from "../lib/i18n";

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
  const { pick } = useI18n();
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
      setError(err instanceof Error ? err.message : pick("Unable to load platform earnings.", "პლატფორმის შემოსავალი ვერ ჩაიტვირთა."));
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
        <div className="ownerHeroEyebrow">{pick("Internal only", "მხოლოდ შიდა გამოყენებისთვის")}</div>
        <div className="ownerHeroBalance">
          {formatMoney(summary?.total_fees_earned ?? "0.00", currency)}
        </div>
        <p className="ownerHeroNote">
          {pick(
            "Platform fee revenue across all fleets. This page is visible only to the ExpertPay internal team.",
            "პლატფორმის საკომისიო შემოსავალი ყველა ფლიტზე. ეს გვერდი მხოლოდ ExpertPay-ის შიდა გუნდს უჩანს."
          )}
        </p>
        <div className="ownerHeroMeta">
          <span>{pick("Platform earnings", "პლატფორმის შემოსავალი")}</span>
          <span>{loading ? pick("Refreshing...", "ახლდება...") : pick(`${summary?.fees_by_fleet.length ?? 0} fleets with fees`, `${summary?.fees_by_fleet.length ?? 0} ფლიტს აქვს საკომისიო`)}</span>
        </div>
      </section>

      {error ? <p className="statusError">{error}</p> : null}

      <section className="ownerStatsGrid" aria-label={pick("Platform earnings overview", "პლატფორმის შემოსავლის მიმოხილვა")}>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("Total fees earned", "ჯამური საკომისიო შემოსავალი")}</div>
          <div className="ownerStatValue">{formatMoney(summary?.total_fees_earned ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("Last 7 days", "ბოლო 7 დღე")}</div>
          <div className="ownerStatValue">{formatMoney(summary?.recent_totals.last_7_days ?? "0.00", currency)}</div>
        </article>
        <article className="card ownerStatCard">
          <div className="ownerStatLabel">{pick("Last 30 days", "ბოლო 30 დღე")}</div>
          <div className="ownerStatValue">{formatMoney(summary?.recent_totals.last_30_days ?? "0.00", currency)}</div>
        </article>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Fees by fleet", "საკომისიოები ფლიტების მიხედვით")}</h2>
        </div>

        {summary?.fees_by_fleet.length ? (
          <div className="txList" role="list">
            {summary.fees_by_fleet.map((fleet) => (
              <div key={fleet.fleet_id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">{fleet.fleet_name}</div>
                  <div className="txSub">{pick("Platform fee revenue from this fleet", "ამ ფლიტიდან მიღებული პლატფორმის საკომისიო")}</div>
                </div>
                <div className="txMeta">
                  <div className="txAmount">{formatMoney(fleet.total_fees_earned, currency)}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="statusHint">{pick("No platform fees have been recorded yet.", "პლატფორმის საკომისიო ჯერ არ დაფიქსირებულა.")}</p>
        )}
      </section>
    </div>
  );
}
