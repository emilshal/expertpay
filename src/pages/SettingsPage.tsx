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
              <div className="txTitle">Wallet vs Ledger</div>
              <div className="txSub">
                Wallet {report.wallet.wallet_balance} / Ledger {report.wallet.ledger_balance} {report.currency}
              </div>
            </div>
            <div className={`txAmount ${report.wallet.status === "OK" ? "pos" : "neg"}`}>
              {report.wallet.delta}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Yandex import vs ledger</div>
              <div className="txSub">
                Imported {report.yandex.imported_total} / Ledger {report.yandex.ledger_total} {report.currency}
              </div>
            </div>
            <div className={`txAmount ${report.yandex.status === "OK" ? "pos" : "neg"}`}>
              {report.yandex.delta}
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Yandex last sync</div>
              <div className="txSub">
                {report.yandex.last_live_sync
                  ? `${report.yandex.last_live_sync.checked_at} | Drivers ${report.yandex.last_live_sync.drivers_fetched} | Transactions ${report.yandex.last_live_sync.transactions_fetched} | Imported ${report.yandex.last_live_sync.imported_count}`
                  : "No live sync yet"}
              </div>
            </div>
            <div className={`txAmount ${report.yandex.last_live_sync?.ok ? "pos" : "neg"}`}>
              {report.yandex.last_live_sync ? (report.yandex.last_live_sync.partial ? "PARTIAL" : report.yandex.last_live_sync.ok ? "OK" : "ERROR") : "N/A"}
            </div>
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
              <div className="txTitle">Withdrawals</div>
              <div className="txSub">
                Total {report.withdrawals.total} | Completed {report.withdrawals.completed_total} | Pending{" "}
                {report.withdrawals.pending_total} | Failed {report.withdrawals.failed_total}
              </div>
            </div>
            <div className="txAmount pos">{report.withdrawals.count}</div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Bank simulator payouts</div>
              <div className="txSub">
                Accepted {report.bank_simulator.totals_by_status.accepted ?? "0.00"} | Processing{" "}
                {report.bank_simulator.totals_by_status.processing ?? "0.00"} | Settled{" "}
                {report.bank_simulator.totals_by_status.settled ?? "0.00"} | Failed{" "}
                {report.bank_simulator.totals_by_status.failed ?? "0.00"}
              </div>
            </div>
            <div className="txAmount pos">{report.bank_simulator.count}</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
