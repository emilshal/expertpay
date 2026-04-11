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
import { useI18n } from "../lib/i18n";

export default function ConnectYandexPage() {
  const { pick } = useI18n();
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
      setError(pick("Unable to load Yandex overview.", "Yandex-ის მიმოხილვა ვერ ჩაიტვირთა."));
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
      setError(err instanceof Error ? err.message : pick("Request failed.", "მოთხოვნა ვერ შესრულდა."));
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
          <h1>{pick("Yandex Overview", "Yandex მიმოხილვა")}</h1>
          <p className="statusHint" style={{ marginTop: "6px" }}>
            {pick("Keep your Yandex fleet data connected and synced into ExpertPay.", "Yandex-ის ფლიტის მონაცემები დაკავშირებული და ExpertPay-ში დასინქული შეინარჩუნეთ.")}
          </p>
        </div>
        <button className="btn btnGhost" type="button" onClick={() => void loadOverview()}>
          {loading ? pick("Loading...", "იტვირთება...") : pick("Refresh", "განახლება")}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list" style={{ marginTop: "14px" }}>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Connection status</div>
            <div className="txTitle">{pick("Connection status", "კავშირის სტატუსი")}</div>
            <div className="txSub">
              {lastConnectionStatus
                ? `${lastConnectionStatus.checked_at} | HTTP ${lastConnectionStatus.http_status ?? "n/a"}`
                : pick("No connection check yet", "კავშირის შემოწმება ჯერ არ ყოფილა")}
            </div>
          </div>
          <div className={`txAmount ${lastConnectionStatus?.ok ? "pos" : "neg"}`}>
            {lastConnectionStatus ? (lastConnectionStatus.ok ? pick("connected", "დაკავშირებულია") : pick("attention", "ყურადღება")) : pick("unknown", "უცნობია")}
          </div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">{pick("Last sync", "ბოლო სინქი")}</div>
            <div className="txSub">
              {lastLiveSync
                ? `${lastLiveSync.checked_at} | ${pick("Drivers", "მძღოლები")} ${lastLiveSync.drivers_fetched} | ${pick("Transactions", "ტრანზაქციები")} ${lastLiveSync.transactions_fetched}`
                : pick("No live sync yet", "ცოცხალი სინქი ჯერ არ ყოფილა")}
            </div>
          </div>
          <div className={`txAmount ${lastLiveSync?.ok ? "pos" : "neg"}`}>
            {lastLiveSync ? (lastLiveSync.partial ? pick("partial", "ნაწილობრივი") : lastLiveSync.ok ? pick("ok", "კარგია") : pick("error", "შეცდომა")) : pick("pending", "მოლოდინში")}
          </div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">{pick("Stored records", "შენახული ჩანაწერები")}</div>
            <div className="txSub">
              {pick("Drivers", "მძღოლები")} {report?.yandex.stored_driver_profiles ?? 0} | {pick("Transactions", "ტრანზაქციები")} {report?.yandex.stored_transactions ?? 0}
            </div>
          </div>
          <div className="txAmount pos">{report?.yandex.sync_runs_count ?? 0}</div>
        </div>

        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">{pick("Ledger import total", "ლეჯერის იმპორტის ჯამი")}</div>
            <div className="txSub">
              {pick("Imported", "იმპორტირებული")} {report?.yandex.imported_total ?? "0.00"} / {pick("Ledger", "ლეჯერი")} {report?.yandex.ledger_total ?? "0.00"}{" "}
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
              setMessage(result.test.ok ? pick("Yandex connection refreshed.", "Yandex კავშირი განახლდა.") : result.test.detail);
              await loadOverview();
            })
          }
        >
          {pick("Refresh Connection Status", "კავშირის სტატუსის განახლება")}
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: false });
              setLastSync(result.sync);
              setMessage(pick("Latest Yandex data synced.", "Yandex-ის ბოლო მონაცემები დასინქდა."));
              await loadOverview();
            })
          }
        >
          {pick("Sync Latest Data", "ბოლო მონაცემების სინქი")}
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: true });
              setLastSync(result.sync);
              setMessage(pick("Full Yandex refresh completed.", "Yandex-ის სრული განახლება დასრულდა."));
              await loadOverview();
            })
          }
        >
          {pick("Full Refresh", "სრული განახლება")}
        </button>

        <Link className="transferSubmit" to="/yandex-data">
          {pick("View Yandex Data", "Yandex მონაცემების ნახვა")}
        </Link>
      </div>

      {connectionTest ? (
        <div className="txList" role="list" style={{ marginTop: "18px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Latest connection refresh</div>
              <div className="txTitle">{pick("Latest connection refresh", "კავშირის ბოლო განახლება")}</div>
              <div className="txSub">{connectionTest.detail}</div>
            </div>
            <div className={`txAmount ${connectionTest.ok ? "pos" : "neg"}`}>
              {connectionTest.ok ? pick("ok", "კარგია") : pick("error", "შეცდომა")}
            </div>
          </div>
        </div>
      ) : null}

      {lastSync ? (
        <div className="txList" role="list" style={{ marginTop: "12px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Latest sync result</div>
              <div className="txTitle">{pick("Latest sync result", "ბოლო სინქის შედეგი")}</div>
              <div className="txSub">{lastSync.detail}</div>
            </div>
            <div className={`txAmount ${lastSync.ok ? "pos" : "neg"}`}>
              {lastSync.partial ? pick("partial", "ნაწილობრივი") : lastSync.ok ? pick("ok", "კარგია") : pick("error", "შეცდომა")}
            </div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Imported to ExpertPay", "ExpertPay-ში იმპორტირებული")}</div>
              <div className="txSub">{pick("New events", "ახალი მოვლენები")} {lastSync.transactions.stored_new_events}</div>
            </div>
            <div className="txAmount pos">{lastSync.transactions.imported_total} GEL</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
