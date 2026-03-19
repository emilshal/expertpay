import { useEffect, useMemo, useState } from "react";
import {
  fleetDriverMappings,
  fleets,
  getActiveFleetName,
  setActiveFleetName,
  updateFleetDriverMapping,
  type DriverYandexMapping,
  type Fleet
} from "../lib/api";

function displayName(mapping: DriverYandexMapping) {
  const fullName = `${mapping.first_name} ${mapping.last_name}`.trim();
  return fullName || mapping.username;
}

export default function DriverMappingsPage() {
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [selectedFleet, setSelectedFleet] = useState(getActiveFleetName() ?? "");
  const [mappings, setMappings] = useState<DriverYandexMapping[]>([]);
  const [draftIds, setDraftIds] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingBindingId, setSavingBindingId] = useState<number | null>(null);

  const canLoad = useMemo(() => Boolean(selectedFleet.trim()), [selectedFleet]);
  const mappedCount = mappings.filter((item) => item.has_mapping).length;
  const unmappedCount = mappings.length - mappedCount;

  async function loadFleets() {
    const data = await fleets();
    setFleetList(data);
    if (!selectedFleet && data.length > 0) {
      setSelectedFleet(data[0].name);
    }
  }

  async function loadMappings() {
    if (!canLoad) return;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await fleetDriverMappings(selectedFleet);
      setMappings(data);
      setDraftIds(Object.fromEntries(data.map((item) => [item.id, item.yandex_external_driver_id ?? ""])));
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only fleet admin/owner")) {
        setError("Only fleet admin/owner can manage Yandex driver mappings.");
      } else {
        setError("Unable to load driver mappings.");
      }
      setMappings([]);
      setDraftIds({});
    } finally {
      setLoading(false);
    }
  }

  async function saveMapping(mapping: DriverYandexMapping) {
    setSavingBindingId(mapping.id);
    setError("");
    setMessage("");
    try {
      await updateFleetDriverMapping({
        binding_id: mapping.id,
        fleet_name: selectedFleet,
        yandex_external_driver_id: (draftIds[mapping.id] ?? "").trim()
      });
      setMessage(`Updated Yandex mapping for ${displayName(mapping)}.`);
      await loadMappings();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("already mapped")) {
        setError("That Yandex external driver ID is already assigned to another driver.");
      } else if (text.includes("another fleet")) {
        setError("This driver is already financially assigned to another fleet.");
      } else {
        setError("Could not update Yandex mapping.");
      }
    } finally {
      setSavingBindingId(null);
    }
  }

  useEffect(() => {
    void loadFleets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedFleet) {
      void loadMappings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFleet]);

  return (
    <section className="card">
      <div className="cardTitleRow">
        <div>
          <h1>Driver Yandex Mappings</h1>
          <div className="txSub">Keep Yandex external driver IDs attached to the right drivers before earnings import.</div>
        </div>
      </div>

      <div className="transferForm">
        <label className="transferField">
          <span className="transferLabel">Fleet</span>
          <span className="transferSelectWrap">
            <select
              className="transferInput"
              value={selectedFleet}
              onChange={(event) => {
                setSelectedFleet(event.target.value);
                if (event.target.value) setActiveFleetName(event.target.value);
              }}
            >
              <option value="">Select fleet</option>
              {fleetList.map((fleet) => (
                <option key={fleet.id} value={fleet.name}>
                  {fleet.name}
                </option>
              ))}
            </select>
          </span>
        </label>

        <button className="btn btnGhost" type="button" onClick={() => void loadMappings()}>
          {loading ? "Loading..." : "Refresh Mappings"}
        </button>
      </div>

      <div className="mappingStats">
        <div className="mappingStat">
          <span className="mappingStatValue">{mappedCount}</span>
          <span className="mappingStatLabel">Mapped</span>
        </div>
        <div className="mappingStat">
          <span className="mappingStatValue">{unmappedCount}</span>
          <span className="mappingStatLabel">Unmapped</span>
        </div>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list">
        {mappings.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No driver mappings loaded</div>
              <div className="txSub">Select a fleet and refresh to review mapped and unmapped drivers.</div>
            </div>
          </div>
        ) : (
          mappings.map((mapping) => (
            <div className="txRow mappingRow" role="listitem" key={mapping.id}>
              <div className="txMain">
                <div className="txTitle">{displayName(mapping)}</div>
                <div className="txSub">
                  {mapping.phone_number} | @{mapping.username} | {mapping.is_active ? "active" : "inactive"}
                </div>
                <div className={`mappingBadge ${mapping.mapping_conflict ? "mappingBadgeWarn" : mapping.has_mapping ? "mappingBadgeOk" : "mappingBadgePending"}`}>
                  {mapping.mapping_conflict
                    ? `Conflict with ${mapping.mapping_conflict_fleet_name || "another fleet"}`
                    : mapping.has_mapping
                      ? "Mapped"
                      : "Unmapped"}
                </div>
              </div>
              <div className="mappingEditor">
                <input
                  className="transferInput"
                  placeholder="Yandex external driver ID"
                  value={draftIds[mapping.id] ?? ""}
                  onChange={(event) =>
                    setDraftIds((prev) => ({
                      ...prev,
                      [mapping.id]: event.target.value
                    }))
                  }
                  disabled={mapping.mapping_conflict}
                />
                <button
                  className="btn btnPrimary"
                  type="button"
                  onClick={() => void saveMapping(mapping)}
                  disabled={savingBindingId === mapping.id || mapping.mapping_conflict}
                >
                  {savingBindingId === mapping.id ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
