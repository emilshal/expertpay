import { useEffect, useMemo, useState } from "react";
import {
  createFleetMember,
  fleets,
  fleetMembers,
  getActiveFleetName,
  setActiveFleetName,
  updateFleetMemberRole,
  type Fleet,
  type FleetMember
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function FleetMembersPage() {
  const { pick } = useI18n();
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [selectedFleet, setSelectedFleet] = useState(getActiveFleetName() ?? "");
  const [members, setMembers] = useState<FleetMember[]>([]);
  const [draftRoles, setDraftRoles] = useState<Record<number, FleetMember["role"]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingMemberId, setSavingMemberId] = useState<number | null>(null);
  const [addingMember, setAddingMember] = useState(false);
  const [newDriverPhone, setNewDriverPhone] = useState("");
  const [newDriverFirstName, setNewDriverFirstName] = useState("");
  const [newDriverLastName, setNewDriverLastName] = useState("");
  const [newDriverEmail, setNewDriverEmail] = useState("");

  const canLoad = useMemo(() => Boolean(selectedFleet.trim()), [selectedFleet]);
  const canAddDriver = useMemo(
    () => Boolean(selectedFleet.trim() && newDriverPhone.trim()),
    [newDriverPhone, selectedFleet]
  );

  async function loadFleets() {
    const data = await fleets();
    setFleetList(data);
    if (!selectedFleet && data.length > 0) {
      setSelectedFleet(data[0].name);
    }
  }

  async function loadMembers() {
    if (!canLoad) return;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await fleetMembers(selectedFleet);
      setMembers(data);
      setDraftRoles(Object.fromEntries(data.map((item) => [item.id, item.role])));
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only fleet admin/owner")) {
        setError(pick("Only fleet admin/owner can manage member roles.", "წევრების როლების მართვა მხოლოდ ფლიტის ადმინს ან მფლობელს შეუძლია."));
      } else {
        setError(pick("Unable to load fleet members.", "ფლიტის წევრები ვერ ჩაიტვირთა."));
      }
      setMembers([]);
      setDraftRoles({});
    } finally {
      setLoading(false);
    }
  }

  async function saveRole(member: FleetMember) {
    const nextRole = draftRoles[member.id];
    if (!nextRole || nextRole === member.role) return;

    setSavingMemberId(member.id);
    setError("");
    setMessage("");
    try {
      await updateFleetMemberRole({
        fleet_name: selectedFleet,
        phone_number: member.phone_number,
        role: nextRole
      });
      setMessage(pick(`Updated ${member.phone_number} to ${nextRole}.`, `${member.phone_number}-ის როლი შეიცვალა: ${nextRole}.`));
      await loadMembers();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only fleet admin/owner")) {
        setError(pick("Only fleet admin/owner can change roles.", "როლების შეცვლა მხოლოდ ფლიტის ადმინს ან მფლობელს შეუძლია."));
      } else if (text.includes("owner")) {
        setError(pick("Owner role can only be changed by owner.", "Owner-ის როლის შეცვლა მხოლოდ owner-ს შეუძლია."));
      } else {
        setError(pick("Could not update member role.", "წევრის როლის განახლება ვერ მოხერხდა."));
      }
    } finally {
      setSavingMemberId(null);
    }
  }

  async function addDriver() {
    if (!canAddDriver) return;

    setAddingMember(true);
    setError("");
    setMessage("");
    try {
      const member = await createFleetMember({
        fleet_name: selectedFleet,
        phone_number: newDriverPhone,
        first_name: newDriverFirstName.trim(),
        last_name: newDriverLastName.trim(),
        email: newDriverEmail.trim(),
        role: "driver"
      });
      setMessage(pick(`Added driver ${member.phone_number}.`, `მძღოლი დაემატა: ${member.phone_number}.`));
      setNewDriverPhone("");
      setNewDriverFirstName("");
      setNewDriverLastName("");
      setNewDriverEmail("");
      await loadMembers();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("already registered")) {
        setError(pick("This phone number is already registered.", "ეს ტელეფონის ნომერი უკვე რეგისტრირებულია."));
      } else if (text.includes("Only fleet admin/owner")) {
        setError(pick("Only fleet admin/owner can add drivers.", "მძღოლის დამატება მხოლოდ ფლიტის ადმინს ან მფლობელს შეუძლია."));
      } else {
        setError(pick("Could not add driver.", "მძღოლის დამატება ვერ მოხერხდა."));
      }
    } finally {
      setAddingMember(false);
    }
  }

  useEffect(() => {
    void loadFleets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedFleet) {
      void loadMembers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFleet]);

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>{pick("Fleet Members", "ფლიტის წევრები")}</h1>
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

        <button className="btn btnGhost" type="button" onClick={() => void loadMembers()}>
          {loading ? pick("Loading...", "იტვირთება...") : pick("Refresh Members", "წევრების განახლება")}
        </button>
      </div>

      <div className="transferForm">
        <div className="cardTitleRow">
          <h2>{pick("Add Driver", "მძღოლის დამატება")}</h2>
        </div>
        <label className="transferField">
          <span className="transferLabel">{pick("Phone number", "ტელეფონის ნომერი")}</span>
          <div className="phoneInputWrap">
            <span className="phonePrefix">+995</span>
            <input
              className="transferInput phoneInput"
              type="tel"
              inputMode="numeric"
              placeholder="598950002"
              value={newDriverPhone}
              onChange={(event) => {
                let value = event.target.value.replace(/\D/g, "");
                if (value.startsWith("995")) value = value.slice(3);
                setNewDriverPhone(value.slice(0, 9));
              }}
            />
          </div>
        </label>
        <div className="authGrid">
          <label className="transferField">
            <span className="transferLabel">{pick("First name", "სახელი")}</span>
            <input
              className="transferInput"
              type="text"
              value={newDriverFirstName}
              onChange={(event) => setNewDriverFirstName(event.target.value)}
            />
          </label>
          <label className="transferField">
            <span className="transferLabel">{pick("Last name", "გვარი")}</span>
            <input
              className="transferInput"
              type="text"
              value={newDriverLastName}
              onChange={(event) => setNewDriverLastName(event.target.value)}
            />
          </label>
        </div>
        <label className="transferField">
          <span className="transferLabel">{pick("Email", "ელფოსტა")}</span>
          <input
            className="transferInput"
            type="email"
            placeholder="driver@example.com"
            value={newDriverEmail}
            onChange={(event) => setNewDriverEmail(event.target.value)}
          />
        </label>
        <button className="btn btnPrimary" type="button" onClick={() => void addDriver()} disabled={!canAddDriver || addingMember}>
          {addingMember ? pick("Adding...", "ემატება...") : pick("Add driver", "მძღოლის დამატება")}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list">
        {members.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No members loaded</div>
              <div className="txTitle">{pick("No members loaded", "წევრები არ ჩაიტვირთა")}</div>
              <div className="txSub">{pick("Select a fleet and refresh.", "აირჩიეთ ფლიტი და განაახლეთ.")}</div>
            </div>
          </div>
        ) : (
          members.map((member) => (
            <div className="txRow" role="listitem" key={member.id}>
              <div className="txMain">
                <div className="txTitle">
                  {member.first_name || member.last_name
                    ? `${member.first_name} ${member.last_name}`.trim()
                    : member.username}
                </div>
                <div className="txSub">
                  {member.phone_number} | @{member.username} | {member.is_active ? pick("active", "აქტიური") : pick("inactive", "არააქტიური")}
                </div>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span className="transferSelectWrap" style={{ minWidth: "130px" }}>
                  <select
                    className="transferInput"
                    value={draftRoles[member.id] ?? member.role}
                    onChange={(event) =>
                      setDraftRoles((prev) => ({
                        ...prev,
                        [member.id]: event.target.value as FleetMember["role"]
                      }))
                    }
                  >
                    <option value="driver">driver</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                    <option value="owner">owner</option>
                  </select>
                </span>
                <button
                  className="btn btnPrimary"
                  type="button"
                  onClick={() => void saveRole(member)}
                  disabled={savingMemberId === member.id}
                >
                  {savingMemberId === member.id ? pick("Saving...", "ინახება...") : pick("Save", "შენახვა")}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
