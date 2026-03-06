import { useEffect, useState } from "react";
import { syncYandexCategories, yandexCategories, yandexSyncRuns, type YandexCategory, type YandexSyncRun } from "../lib/api";

export default function YandexOpsPage() {
  const [categories, setCategories] = useState<YandexCategory[]>([]);
  const [runs, setRuns] = useState<YandexSyncRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncingCategories, setSyncingCategories] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const [cats, syncRuns] = await Promise.all([yandexCategories(), yandexSyncRuns()]);
      setCategories(cats);
      setRuns(syncRuns);
    } catch {
      setError("Unable to load Yandex Ops data.");
    } finally {
      setLoading(false);
    }
  }

  async function runCategorySync() {
    setSyncingCategories(true);
    setError("");
    setMessage("");
    try {
      const result = await syncYandexCategories();
      const payload = result.categories_sync as {
        ok?: boolean;
        fetched?: number;
        upserted?: number;
        detail?: string;
      };
      setMessage(
        `${payload.detail ?? "Category sync finished"} (fetched ${payload.fetched ?? 0}, upserted ${
          payload.upserted ?? 0
        })`
      );
      await loadAll();
    } catch {
      setError("Category sync failed.");
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
        <h1>Yandex Ops</h1>
        <div style={{ display: "flex", gap: "8px" }}>
          <button className="btn btnGhost" type="button" onClick={() => void loadAll()}>
            {loading ? "Loading..." : "Refresh"}
          </button>
          <button className="btn btnPrimary" type="button" onClick={() => void runCategorySync()}>
            {syncingCategories ? "Syncing..." : "Sync Categories"}
          </button>
        </div>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <h2 className="h2" style={{ marginTop: "8px" }}>
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
          categories.map((category) => (
            <div className="txRow" role="listitem" key={category.id}>
              <div className="txMain">
                <div className="txTitle">{category.name}</div>
                <div className="txSub">
                  {category.code || category.external_category_id} | updated {category.updated_at}
                </div>
              </div>
              <div className={`txAmount ${category.is_creatable ? "pos" : "neg"}`}>
                {category.is_creatable ? "CREATABLE" : "READ-ONLY"}
              </div>
            </div>
          ))
        )}
      </div>

      <h2 className="h2" style={{ marginTop: "18px" }}>
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
          runs.slice(0, 20).map((run) => (
            <div className="txRow" role="listitem" key={run.id}>
              <div className="txMain">
                <div className="txTitle">
                  {run.trigger.toUpperCase()} | {run.status.toUpperCase()}
                </div>
                <div className="txSub">
                  {run.created_at} | tx fetched {run.transactions_fetched} | imported {run.imported_count}
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
