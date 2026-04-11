import { useEffect, useState } from "react";
import {
  syncYandexCategories,
  yandexCategories,
  yandexDriverDetail,
  yandexDriverSummaries,
  yandexEvents,
  yandexSyncRuns,
  yandexTransactions,
  type YandexCategory,
  type YandexDriverDetail,
  type YandexDriverSummary,
  type YandexEvent,
  type YandexSyncRun,
  type YandexTransactionRecord
} from "../lib/api";
import { useI18n } from "../lib/i18n";

function displayDriverName(driver: YandexDriverSummary["driver"]) {
  const name = `${driver.first_name} ${driver.last_name}`.trim();
  return name || driver.external_driver_id;
}

export default function YandexOpsPage() {
  const { pick } = useI18n();
  const [categories, setCategories] = useState<YandexCategory[]>([]);
  const [driverSummaries, setDriverSummaries] = useState<YandexDriverSummary[]>([]);
  const [transactions, setTransactions] = useState<YandexTransactionRecord[]>([]);
  const [events, setEvents] = useState<YandexEvent[]>([]);
  const [runs, setRuns] = useState<YandexSyncRun[]>([]);
  const [selectedDriver, setSelectedDriver] = useState<YandexDriverDetail | null>(null);
  const [selectedDriverId, setSelectedDriverId] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncingCategories, setSyncingCategories] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [cats, driverRows, txRows, eventRows, syncRuns] = await Promise.all([
        yandexCategories(),
        yandexDriverSummaries(),
        yandexTransactions(),
        yandexEvents(),
        yandexSyncRuns()
      ]);
      setCategories(cats);
      setDriverSummaries(driverRows);
      setTransactions(txRows);
      setEvents(eventRows);
      setRuns(syncRuns);
    } catch {
      setError(pick("Unable to load Yandex data.", "Yandex მონაცემები ვერ ჩაიტვირთა."));
    } finally {
      setLoading(false);
    }
  }

  async function openDriver(externalDriverId: string) {
    try {
      setSelectedDriverId(externalDriverId);
      const detail = await yandexDriverDetail(externalDriverId);
      setSelectedDriver(detail);
    } catch {
      setError(pick("Unable to load driver detail.", "მძღოლის დეტალები ვერ ჩაიტვირთა."));
    } finally {
      setSelectedDriverId("");
    }
  }

  async function runCategorySync() {
    setSyncingCategories(true);
    setError("");
    setMessage("");
    try {
      const result = await syncYandexCategories();
      const payload = result.categories_sync as {
        fetched?: number;
        upserted?: number;
        detail?: string;
      };
      setMessage(
        `${payload.detail ?? pick("Category sync finished", "კატეგორიების სინქი დასრულდა")} (${pick("fetched", "მოწოდებული")} ${payload.fetched ?? 0}, ${pick("upserted", "განახლებული")} ${
          payload.upserted ?? 0
        })`
      );
      await loadAll();
    } catch {
      setError(pick("Category sync failed.", "კატეგორიების სინქი ვერ შესრულდა."));
    } finally {
      setSyncingCategories(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  return (
    <section className="card">
      <div className="cardTitleRow">
        <div>
          <h1>{pick("Yandex Data", "Yandex მონაცემები")}</h1>
          <p className="statusHint" style={{ marginTop: "6px" }}>
            {pick("Browse synced drivers, normalized transactions, raw events, categories, and recent sync runs.", "დაათვალიერეთ დასინქული მძღოლები, ნორმალიზებული ტრანზაქციები, ნედლი მოვლენები, კატეგორიები და ბოლო სინქის გაშვებები.")}
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="btn btnGhost" type="button" onClick={() => void loadAll()}>
            {loading ? pick("Loading...", "იტვირთება...") : pick("Refresh", "განახლება")}
          </button>
          <button className="btn btnPrimary" type="button" onClick={() => void runCategorySync()}>
            {syncingCategories ? pick("Syncing...", "სინქდება...") : pick("Sync Categories", "კატეგორიების სინქი")}
          </button>
        </div>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list" style={{ marginTop: "14px" }}>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Drivers</div>
            <div className="txSub">Profiles with per-driver earnings totals</div>
          </div>
          <div className="txAmount pos">{driverSummaries.length}</div>
        </div>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Transactions</div>
            <div className="txSub">Normalized transaction rows stored locally</div>
          </div>
          <div className="txAmount pos">{transactions.length}</div>
        </div>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Raw Events</div>
            <div className="txSub">Latest raw imported Yandex events</div>
          </div>
          <div className="txAmount">{events.length}</div>
        </div>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Categories</div>
            <div className="txSub">Category mapping available for this fleet</div>
          </div>
          <div className="txAmount">{categories.length}</div>
        </div>
        <div className="txRow" role="listitem">
          <div className="txMain">
            <div className="txTitle">Sync Runs</div>
            <div className="txSub">Recent live and scheduler sync history</div>
          </div>
          <div className="txAmount">{runs.length}</div>
        </div>
      </div>

      <h2 className="h2" style={{ marginTop: "20px" }}>
        Drivers
      </h2>
      <div className="txList" role="list">
        {driverSummaries.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No driver profiles synced yet</div>
            </div>
          </div>
        ) : (
          driverSummaries.slice(0, 50).map((item) => (
            <button
              className="txRow txRowButton"
              type="button"
              role="listitem"
              key={item.driver.id}
              onClick={() => void openDriver(item.driver.external_driver_id)}
            >
              <div className="txMain">
                <div className="txTitle">{displayDriverName(item.driver)}</div>
                <div className="txSub">
                  Earned {item.summary.total_earned} {item.summary.currency} | Deductions {item.summary.total_deductions}{" "}
                  {item.summary.currency}
                </div>
                <div className="txSub">
                  {item.driver.phone_number || "No phone"} | {item.driver.external_driver_id}
                </div>
              </div>
              <div className="txAmount pos">
                {item.summary.net_total} {item.summary.currency}
              </div>
            </button>
          ))
        )}
      </div>

      {selectedDriver ? (
        <>
          <h2 className="h2" style={{ marginTop: "20px" }}>
            Driver Detail
          </h2>
          <div className="txList" role="list">
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{displayDriverName(selectedDriver.driver)}</div>
                <div className="txSub">
                  {selectedDriver.driver.phone_number || "No phone"} | {selectedDriver.driver.external_driver_id}
                </div>
                <div className="txSub">Status {selectedDriver.driver.status || "unknown"}</div>
              </div>
              <div className="txAmount pos">{selectedDriver.summary.net_total} {selectedDriver.summary.currency}</div>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">Summary</div>
                <div className="txSub">Transactions {selectedDriver.summary.transaction_count}</div>
                <div className="txSub">Earned {selectedDriver.summary.total_earned} {selectedDriver.summary.currency}</div>
                <div className="txSub">
                  Deductions {selectedDriver.summary.total_deductions} {selectedDriver.summary.currency}
                </div>
              </div>
              <div className="txAmount">{selectedDriver.summary.last_transaction_at || "No activity"}</div>
            </div>
            {selectedDriver.recent_transactions.slice(0, 20).map((tx) => (
              <div className="txRow" role="listitem" key={tx.id}>
                <div className="txMain">
                  <div className="txTitle">{tx.category || "transaction"}</div>
                  <div className="txSub">{tx.event_at || "No timestamp"}</div>
                </div>
                <div className={`txAmount ${tx.direction === "credit" ? "pos" : tx.direction === "debit" ? "neg" : ""}`}>
                  {tx.amount} {tx.currency}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : selectedDriverId ? (
        <p className="statusHint" style={{ marginTop: "18px" }}>Loading driver detail...</p>
      ) : null}

      <h2 className="h2" style={{ marginTop: "20px" }}>
        Transactions
      </h2>
      <div className="txList" role="list">
        {transactions.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No transactions synced yet</div>
            </div>
          </div>
        ) : (
          transactions.slice(0, 50).map((tx) => (
            <div className="txRow" role="listitem" key={tx.id}>
              <div className="txMain">
                <div className="txTitle">
                  {tx.category || "transaction"} | {tx.external_transaction_id}
                </div>
                <div className="txSub">
                  Driver {tx.driver_external_id || "n/a"} | {tx.event_at || "No timestamp"}
                </div>
              </div>
              <div className={`txAmount ${tx.direction === "credit" ? "pos" : tx.direction === "debit" ? "neg" : ""}`}>
                {tx.amount} {tx.currency}
              </div>
            </div>
          ))
        )}
      </div>

      <h2 className="h2" style={{ marginTop: "20px" }}>
        Raw Events
      </h2>
      <div className="txList" role="list">
        {events.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No raw events loaded yet</div>
            </div>
          </div>
        ) : (
          events.slice(0, 30).map((event) => (
            <div className="txRow" role="listitem" key={event.id}>
              <div className="txMain">
                <div className="txTitle">
                  {event.event_type} | {event.external_id}
                </div>
                <div className="txSub">{event.created_at}</div>
              </div>
              <div className={`txAmount ${event.processed ? "pos" : "neg"}`}>{event.processed ? "processed" : "pending"}</div>
            </div>
          ))
        )}
      </div>

      <h2 className="h2" style={{ marginTop: "20px" }}>
        Categories
      </h2>
      <div className="txList" role="list">
        {categories.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No categories synced yet</div>
            </div>
          </div>
        ) : (
          categories.slice(0, 50).map((category) => (
            <div className="txRow" role="listitem" key={category.id}>
              <div className="txMain">
                <div className="txTitle">{category.name}</div>
                <div className="txSub">
                  {category.code || category.external_category_id} | updated {category.updated_at}
                </div>
              </div>
              <div className={`txAmount ${category.is_creatable ? "pos" : "neg"}`}>
                {category.is_creatable ? "creatable" : "read-only"}
              </div>
            </div>
          ))
        )}
      </div>

      <h2 className="h2" style={{ marginTop: "20px" }}>
        Recent Sync Runs
      </h2>
      <div className="txList" role="list">
        {runs.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No sync runs yet</div>
            </div>
          </div>
        ) : (
          runs.slice(0, 30).map((run) => (
            <div className="txRow" role="listitem" key={run.id}>
              <div className="txMain">
                <div className="txTitle">
                  {run.trigger.toUpperCase()} | {run.status.toUpperCase()}
                </div>
                <div className="txSub">
                  {run.created_at} | drivers {run.drivers_fetched} | tx {run.transactions_fetched}
                </div>
                <div className="txSub">{run.detail}</div>
              </div>
              <div className={`txAmount ${run.status === "error" ? "neg" : "pos"}`}>
                {run.imported_total} GEL
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
