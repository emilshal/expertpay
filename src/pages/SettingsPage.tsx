import { useEffect, useState } from "react";
import { reconciliationSummary, type ReconciliationSummary } from "../lib/api";

export default function SettingsPage() {
  const [report, setReport] = useState<ReconciliationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadReport() {
    setLoading(true);
    setError("");
    try {
      const data = await reconciliationSummary();
      setReport(data);
    } catch {
      setError("Unable to load reconciliation report.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReport();
  }, []);

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>Reconciliation</h1>
        <button className="btn btnGhost" type="button" onClick={() => void loadReport()}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}

      {report ? (
        <div className="txList" role="list">
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Overall status</div>
              <div className="txSub">{report.generated_at}</div>
            </div>
            <div className={`txAmount ${report.overall_status === "OK" ? "pos" : "neg"}`}>
              {report.overall_status}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Treasury</div>
              <div className="txSub">Balance {report.treasury.balance} {report.currency}</div>
              <div className="txSub">Expected internal total {report.treasury.expected_total} {report.currency}</div>
            </div>
            <div className={`txAmount ${report.treasury.status === "OK" ? "pos" : "neg"}`}>
              {report.treasury.delta}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Fleet reserves</div>
              <div className="txSub">Total {report.fleet_reserves.total_balance} {report.currency}</div>
              <div className="txSub">Accounts {report.fleet_reserves.account_count}</div>
            </div>
            <div className="txAmount pos">{report.fleet_reserves.account_count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Driver available balances</div>
              <div className="txSub">Total {report.driver_available.total_balance} {report.currency}</div>
              <div className="txSub">Accounts {report.driver_available.account_count}</div>
            </div>
            <div className="txAmount pos">{report.driver_available.account_count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Pending payouts / clearing</div>
              <div className="txSub">Clearing {report.payout_clearing.balance} {report.currency}</div>
              <div className="txSub">
                Pending withdrawals {report.payout_clearing.pending_withdrawals_total} {report.currency}
              </div>
            </div>
            <div className="txAmount pos">{report.payout_clearing.pending_withdrawals_count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Platform fees</div>
              <div className="txSub">Collected {report.platform_fees.balance} {report.currency}</div>
            </div>
            <div className="txAmount pos">{report.platform_fees.balance}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Yandex import vs ledger</div>
              <div className="txSub">Imported {report.yandex.imported_total} {report.currency}</div>
              <div className="txSub">Ledger {report.yandex.ledger_total} {report.currency}</div>
            </div>
            <div className={`txAmount ${report.yandex.status === "OK" ? "pos" : "neg"}`}>
              {report.yandex.delta}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Yandex last sync</div>
              {report.yandex.last_live_sync ? (
                <>
                  <div className="txSub">{report.yandex.last_live_sync.checked_at}</div>
                  <div className="txSub">
                    Drivers {report.yandex.last_live_sync.drivers_fetched} | Upserted{" "}
                    {report.yandex.last_live_sync.drivers_upserted ?? 0}
                  </div>
                  <div className="txSub">
                    Transactions {report.yandex.last_live_sync.transactions_fetched} | Imported{" "}
                    {report.yandex.last_live_sync.imported_count}
                  </div>
                </>
              ) : (
                <div className="txSub">No live sync yet</div>
              )}
            </div>
            <div className={`txAmount ${report.yandex.last_live_sync?.ok ? "pos" : "neg"}`}>
              {report.yandex.last_live_sync ? (report.yandex.last_live_sync.partial ? "PARTIAL" : report.yandex.last_live_sync.ok ? "OK" : "ERROR") : "N/A"}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Stored Yandex records</div>
              <div className="txSub">Driver profiles {report.yandex.stored_driver_profiles ?? 0}</div>
              <div className="txSub">Transactions {report.yandex.stored_transactions ?? 0}</div>
              <div className="txSub">Categories {report.yandex.stored_categories ?? 0}</div>
            </div>
            <div className="txAmount pos">{report.yandex.sync_runs_count ?? 0}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Yandex cursor window</div>
              <div className="txSub">
                {report.yandex.last_transaction_cursor
                  ? `From ${report.yandex.last_transaction_cursor.from} -> To ${report.yandex.last_transaction_cursor.to}`
                  : "No cursor yet"}
              </div>
            </div>
            <div className="txAmount">
              {report.yandex.last_transaction_cursor?.next_from ?? "N/A"}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Deposits</div>
              <div className="txSub">Matched {report.deposits.matched_total} {report.currency}</div>
              <div className="txSub">Unmatched transfers {report.deposits.unmatched_count}</div>
            </div>
            <div className="txAmount pos">{report.deposits.matched_count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Bank simulator payouts</div>
              <div className="txSub">Accepted {report.bank_simulator.totals_by_status.accepted ?? "0.00"}</div>
              <div className="txSub">Processing {report.bank_simulator.totals_by_status.processing ?? "0.00"}</div>
              <div className="txSub">Settled {report.bank_simulator.totals_by_status.settled ?? "0.00"}</div>
              <div className="txSub">Failed {report.bank_simulator.totals_by_status.failed ?? "0.00"}</div>
            </div>
            <div className="txAmount pos">{report.bank_simulator.count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Bank of Georgia payouts</div>
              <div className="txSub">Accepted {report.bog.totals_by_status.accepted ?? "0.00"}</div>
              <div className="txSub">Processing {report.bog.totals_by_status.processing ?? "0.00"}</div>
              <div className="txSub">Settled {report.bog.totals_by_status.settled ?? "0.00"}</div>
              <div className="txSub">Failed {report.bog.totals_by_status.failed ?? "0.00"}</div>
            </div>
            <div className="txAmount pos">{report.bog.count}</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
