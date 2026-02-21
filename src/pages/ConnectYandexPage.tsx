import { useState } from "react";
import {
  connectYandex,
  importYandexEvents,
  reconcileYandex,
  simulateYandexEvents,
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
      <h1>Connect Yandex (Sandbox)</h1>
      <p>Use this to simulate earnings, import to ledger, and reconcile before real Yandex access.</p>

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
