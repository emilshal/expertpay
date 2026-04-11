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
import { useI18n } from "../lib/i18n";

function displayName(mapping: DriverYandexMapping) {
  const fullName = `${mapping.first_name} ${mapping.last_name}`.trim();
  return fullName || mapping.username;
}

export default function DriverMappingsPage() {
  const { pick } = useI18n();
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
        setError(pick("Only fleet admin/owner can manage Yandex driver mappings.", "Yandex-ის მიბმების მართვა მხოლოდ ფლიტის ადმინს ან მფლობელს შეუძლია."));
      } else {
        setError(pick("Unable to load driver mappings.", "მძღოლების მიბმები ვერ ჩაიტვირთა."));
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
      setMessage(pick(`Updated Yandex mapping for ${displayName(mapping)}.`, `${displayName(mapping)}-სთვის Yandex-ის მიბმა განახლდა.`));
      await loadMappings();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("already mapped")) {
        setError(pick("That Yandex external driver ID is already assigned to another driver.", "Yandex-ის ეს გარე მძღოლის ID უკვე სხვა მძღოლზეა მიბმული."));
      } else if (text.includes("another fleet")) {
        setError(pick("This driver is already financially assigned to another fleet.", "ეს მძღოლი უკვე სხვა ფლიტზეა ფინანსურად მიბმული."));
      } else {
        setError(pick("Could not update Yandex mapping.", "Yandex-ის მიბმის განახლება ვერ მოხერხდა."));
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
          <h1>{pick("Driver Yandex Mappings", "მძღოლების Yandex მიბმები")}</h1>
          <div className="txSub">{pick("Keep Yandex external driver IDs attached to the right drivers before earnings import.", "შემოსავლის იმპორტამდე Yandex-ის გარე მძღოლის ID სწორ მძღოლებზე უნდა იყოს მიბმული.")}</div>
        </div>
      </div>

      <div className="transferForm">
        <label className="transferField">
          <span className="transferLabel">{pick("Fleet", "ფლიტი")}</span>
          <span className="transferSelectWrap">
            <select
              className="transferInput"
              value={selectedFleet}
              onChange={(event) => {
                setSelectedFleet(event.target.value);
                if (event.target.value) setActiveFleetName(event.target.value);
              }}
            >
              <option value="">{pick("Select fleet", "აირჩიეთ ფლიტი")}</option>
              {fleetList.map((fleet) => (
                <option key={fleet.id} value={fleet.name}>
                  {fleet.name}
                </option>
              ))}
            </select>
          </span>
        </label>

        <button className="btn btnGhost" type="button" onClick={() => void loadMappings()}>
          {loading ? pick("Loading...", "იტვირთება...") : pick("Refresh Mappings", "მიბმების განახლება")}
        </button>
      </div>

      <div className="mappingStats">
        <div className="mappingStat">
          <span className="mappingStatValue">{mappedCount}</span>
          <span className="mappingStatLabel">{pick("Mapped", "მიბმული")}</span>
        </div>
        <div className="mappingStat">
          <span className="mappingStatValue">{unmappedCount}</span>
          <span className="mappingStatLabel">{pick("Unmapped", "დაუმიბმავი")}</span>
        </div>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list">
        {mappings.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("No driver mappings loaded", "მძღოლების მიბმები არ ჩაიტვირთა")}</div>
              <div className="txSub">{pick("Select a fleet and refresh to review mapped and unmapped drivers.", "აირჩიეთ ფლიტი და განაახლეთ, რომ ნახოთ მიბმული და დაუმიბმავი მძღოლები.")}</div>
            </div>
          </div>
        ) : (
          mappings.map((mapping) => (
            <div className="txRow mappingRow" role="listitem" key={mapping.id}>
              <div className="txMain">
                <div className="txTitle">{displayName(mapping)}</div>
                <div className="txSub">
                  {mapping.phone_number} | @{mapping.username} | {mapping.is_active ? pick("active", "აქტიური") : pick("inactive", "არააქტიური")}
                </div>
                <div className={`mappingBadge ${mapping.mapping_conflict ? "mappingBadgeWarn" : mapping.has_mapping ? "mappingBadgeOk" : "mappingBadgePending"}`}>
                  {mapping.mapping_conflict
                    ? pick(`Conflict with ${mapping.mapping_conflict_fleet_name || "another fleet"}`, `კონფლიქტი: ${mapping.mapping_conflict_fleet_name || "სხვა ფლიტი"}`)
                    : mapping.has_mapping
                      ? pick("Mapped", "მიბმული")
                      : pick("Unmapped", "დაუმიბმავი")}
                </div>
              </div>
              <div className="mappingEditor">
                <input
                  className="transferInput"
                  placeholder={pick("Yandex external driver ID", "Yandex-ის გარე მძღოლის ID")}
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
                  {savingBindingId === mapping.id ? pick("Saving...", "ინახება...") : pick("Save", "შენახვა")}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
