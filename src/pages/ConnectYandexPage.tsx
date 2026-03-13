import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  reconciliationSummary,
  syncLiveYandex,
  testYandexConnection,
  type ReconciliationSummary,
  type YandexConnectionTestResult,
  type YandexLiveSyncResult
} from "../lib/api";

export default function ConnectYandexPage() {
  const [report, setReport] = useState<ReconciliationSummary | null>(null);
  const [connectionTest, setConnectionTest] = useState<YandexConnectionTestResult | null>(null);
  const [lastSync, setLastSync] = useState<YandexLiveSyncResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadOverview() {
    setLoading(true);
    setError("");
    try {
      const data = await reconciliationSummary();
      setReport(data);
    } catch {
      setError("Unable to load Yandex overview.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadOverview();
  }, []);

  async function run(action: () => Promise<void>) {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  }

  const lastConnectionStatus = report?.yandex.last_connection_test;
  const lastLiveSync = report?.yandex.last_live_sync;

  return (
    <section className="card">
      <div className="cardTitleRow">
        <div>
          <h1>Yandex Overview</h1>
          <p className="statusHint" style={{ marginTop: "6px" }}>
            Keep your Yandex fleet data connected and synced into ExpertPay.
          </p>
        </div>
        <button className="btn btnGhost" type="button" onClick={() => void loadOverview()}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list" style={{ marginTop: "14px" }}>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Connection status</div>
            <div className="txSub">
              {lastConnectionStatus
                ? `${lastConnectionStatus.checked_at} | HTTP ${lastConnectionStatus.http_status ?? "n/a"}`
                : "No connection check yet"}
            </div>
          </div>
          <div className={`txAmount ${lastConnectionStatus?.ok ? "pos" : "neg"}`}>
            {lastConnectionStatus ? (lastConnectionStatus.ok ? "connected" : "attention") : "unknown"}
          </div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Last sync</div>
            <div className="txSub">
              {lastLiveSync
                ? `${lastLiveSync.checked_at} | Drivers ${lastLiveSync.drivers_fetched} | Transactions ${lastLiveSync.transactions_fetched}`
                : "No live sync yet"}
            </div>
          </div>
          <div className={`txAmount ${lastLiveSync?.ok ? "pos" : "neg"}`}>
            {lastLiveSync ? (lastLiveSync.partial ? "partial" : lastLiveSync.ok ? "ok" : "error") : "pending"}
          </div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Stored records</div>
            <div className="txSub">
              Drivers {report?.yandex.stored_driver_profiles ?? 0} | Transactions {report?.yandex.stored_transactions ?? 0}
            </div>
          </div>
          <div className="txAmount pos">{report?.yandex.sync_runs_count ?? 0}</div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Ledger import total</div>
            <div className="txSub">
              Imported {report?.yandex.imported_total ?? "0.00"} / Ledger {report?.yandex.ledger_total ?? "0.00"}{" "}
              {report?.currency ?? "GEL"}
            </div>
          </div>
          <div className={`txAmount ${report?.yandex.status === "OK" ? "pos" : "neg"}`}>
            {report?.yandex.status ?? "unknown"}
          </div>
        </div>
      </div>

      <div className="transferForm" style={{ marginTop: "18px" }}>
        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await testYandexConnection();
              setConnectionTest(result.test);
              setMessage(result.test.ok ? "Yandex connection refreshed." : result.test.detail);
              await loadOverview();
            })
          }
        >
          Refresh Connection Status
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: false });
              setLastSync(result.sync);
              setMessage("Latest Yandex data synced.");
              await loadOverview();
            })
          }
        >
          Sync Latest Data
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: true });
              setLastSync(result.sync);
              setMessage("Full Yandex refresh completed.");
              await loadOverview();
            })
          }
        >
          Full Refresh
        </button>

        <Link className="transferSubmit" to="/yandex-data">
          View Yandex Data
        </Link>
      </div>

      {connectionTest ? (
        <div className="txList" role="list" style={{ marginTop: "18px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Latest connection refresh</div>
              <div className="txSub">{connectionTest.detail}</div>
            </div>
            <div className={`txAmount ${connectionTest.ok ? "pos" : "neg"}`}>
              {connectionTest.ok ? "ok" : "error"}
            </div>
          </div>
        </div>
      ) : null}

      {lastSync ? (
        <div className="txList" role="list" style={{ marginTop: "12px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Latest sync result</div>
              <div className="txSub">{lastSync.detail}</div>
            </div>
            <div className={`txAmount ${lastSync.ok ? "pos" : "neg"}`}>
              {lastSync.partial ? "partial" : lastSync.ok ? "ok" : "error"}
            </div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Imported to ExpertPay</div>
              <div className="txSub">New events {lastSync.transactions.stored_new_events}</div>
            </div>
            <div className="txAmount pos">{lastSync.transactions.imported_total} GEL</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
