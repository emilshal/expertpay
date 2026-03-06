import { useState } from "react";
import {
  connectYandex,
  importYandexEvents,
  reconcileYandex,
  simulateYandexEvents,
  syncLiveYandex,
  syncYandexCategories,
  testYandexConnection,
  type YandexLiveSyncResult,
  type YandexConnectionTestResult,
  yandexEvents
} from "../lib/api";

export default function ConnectYandexPage() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<"steady" | "spiky" | "adjustment" | "duplicates" | "out_of_order">(
    "steady"
  );
  const [count, setCount] = useState(10);
  const [reconcile, setReconcile] = useState<{
    imported_events: number;
    imported_total: string;
    ledger_total: string;
    delta: string;
    status: "OK" | "MISMATCH";
  } | null>(null);
  const [connectionTest, setConnectionTest] = useState<YandexConnectionTestResult | null>(null);
  const [liveSync, setLiveSync] = useState<YandexLiveSyncResult | null>(null);
  const [events, setEvents] = useState<Array<{ id: number; external_id: string; processed: boolean }>>([]);

  async function run(action: () => Promise<void>) {
    setLoading(true);
    setMessage("");
    try {
      await action();
    } catch (error) {
      const text = error instanceof Error ? error.message : "Request failed";
      setMessage(text);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h1>Connect Yandex</h1>
      <p>Test live credentials, then simulate/import/reconcile safely before moving full flows to live mode.</p>

      <div className="transferForm">
        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const data = await connectYandex();
              setMessage(`Connected simulator: ${data.external_account_id}`);
            })
          }
        >
          {loading ? "Please wait..." : "Connect Yandex Simulator"}
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await testYandexConnection();
              setConnectionTest(result.test);
              if (result.test.ok) {
                setMessage(`Live check passed (HTTP ${result.test.http_status ?? "n/a"})`);
              } else {
                setMessage(`Live check failed: ${result.test.detail}`);
              }
            })
          }
        >
          Test Live Credentials
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: false });
              setLiveSync(result.sync);
              setMessage(result.sync.detail);
            })
          }
        >
          Sync Live Data (Incremental)
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncLiveYandex({ limit: 100, dry_run: false, full_sync: true });
              setLiveSync(result.sync);
              setMessage(result.sync.detail);
            })
          }
        >
          Full Sync (Last 7 Days)
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncYandexCategories();
              const syncResult = result.categories_sync as {
                ok?: boolean;
                fetched?: number;
                upserted?: number;
                detail?: string;
              };
              setMessage(
                `${syncResult.detail ?? "Category sync finished"} (fetched ${syncResult.fetched ?? 0}, upserted ${
                  syncResult.upserted ?? 0
                })`
              );
            })
          }
        >
          Sync Categories
        </button>

        <label className="transferField">
          <span className="transferLabel">Mode</span>
          <span className="transferSelectWrap">
            <select
              className="transferInput"
              value={mode}
              onChange={(event) => setMode(event.target.value as typeof mode)}
            >
              <option value="steady">steady</option>
              <option value="spiky">spiky</option>
              <option value="adjustment">adjustment</option>
              <option value="duplicates">duplicates</option>
              <option value="out_of_order">out_of_order</option>
            </select>
          </span>
        </label>

        <label className="transferField">
          <span className="transferLabel">Event count</span>
          <input
            className="transferInput"
            type="number"
            min={1}
            max={100}
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
          />
        </label>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await simulateYandexEvents({ mode, count });
              setMessage(`Simulated ${result.stored_count} events (${result.mode})`);
            })
          }
        >
          Simulate Events
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await importYandexEvents();
              setMessage(`Imported ${result.imported_count} events for ${result.imported_total} GEL`);
            })
          }
        >
          Import To Ledger
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await reconcileYandex();
              setReconcile(result);
              setMessage(`Reconciliation: ${result.status}`);
            })
          }
        >
          Reconcile
        </button>

        <button
          className="transferSubmit"
          type="button"
          onClick={() =>
            void run(async () => {
              const list = await yandexEvents();
              setEvents(list.map((item) => ({ id: item.id, external_id: item.external_id, processed: item.processed })));
              setMessage(`Loaded ${list.length} events`);
            })
          }
        >
          Load Events
        </button>
      </div>

      {message ? <p className="statusHint">{message}</p> : null}

      {connectionTest ? (
        <div className="txList" role="list">
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Live credential check</div>
              <div className="txSub">{connectionTest.detail}</div>
            </div>
            <div className={`txAmount ${connectionTest.ok ? "pos" : "neg"}`}>
              {connectionTest.ok ? "PASS" : "FAIL"}
            </div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Mode</div>
              <div className="txSub">{connectionTest.endpoint}</div>
            </div>
            <div className="txAmount">{connectionTest.mode}</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">HTTP status</div>
            </div>
            <div className="txAmount">{connectionTest.http_status ?? "n/a"}</div>
          </div>
        </div>
      ) : null}

      {liveSync ? (
        <div className="txList" role="list" style={{ marginTop: "12px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Live sync status</div>
              <div className="txSub">{liveSync.detail}</div>
            </div>
            <div className={`txAmount ${liveSync.ok ? "pos" : "neg"}`}>
              {liveSync.partial ? "PARTIAL" : liveSync.ok ? "OK" : "ERROR"}
            </div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Drivers fetched</div>
              <div className="txSub">
                HTTP {liveSync.drivers.http_status ?? "n/a"} | Upserted {liveSync.drivers.upserted_profiles ?? 0}
              </div>
            </div>
            <div className="txAmount">{liveSync.drivers.fetched}</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Transactions fetched</div>
              <div className="txSub">HTTP {liveSync.transactions.http_status ?? "n/a"}</div>
            </div>
            <div className="txAmount">{liveSync.transactions.fetched}</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Imported to ledger</div>
              <div className="txSub">New external events: {liveSync.transactions.stored_new_events}</div>
            </div>
            <div className="txAmount pos">{liveSync.transactions.imported_total} GEL</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Cursor</div>
              <div className="txSub">
                {liveSync.cursor ? `${liveSync.cursor.from} -> ${liveSync.cursor.to}` : "No cursor returned"}
              </div>
            </div>
            <div className="txAmount">{liveSync.cursor?.next_from ?? "n/a"}</div>
          </div>
        </div>
      ) : null}

      {reconcile ? (
        <div className="txList" role="list">
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Imported events</div>
              <div className="txSub">Status: {reconcile.status}</div>
            </div>
            <div className="txAmount pos">{reconcile.imported_events}</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Imported total</div>
            </div>
            <div className="txAmount pos">{reconcile.imported_total} GEL</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Ledger total</div>
            </div>
            <div className="txAmount pos">{reconcile.ledger_total} GEL</div>
          </div>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">Delta</div>
            </div>
            <div className={`txAmount ${reconcile.delta === "0.00" ? "pos" : "neg"}`}>{reconcile.delta} GEL</div>
          </div>
        </div>
      ) : null}

      {events.length ? (
        <>
          <h2 className="h2" style={{ marginTop: "18px" }}>
            Recent external events
          </h2>
          <div className="txList" role="list">
            {events.slice(0, 10).map((event) => (
              <div key={event.id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">{event.external_id}</div>
                  <div className="txSub">{event.processed ? "processed" : "pending"}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
