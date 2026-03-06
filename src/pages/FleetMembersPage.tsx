import { useEffect, useMemo, useState } from "react";
import {
  fleets,
  fleetMembers,
  getActiveFleetName,
  setActiveFleetName,
  updateFleetMemberRole,
  type Fleet,
  type FleetMember
} from "../lib/api";

export default function FleetMembersPage() {
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [selectedFleet, setSelectedFleet] = useState(getActiveFleetName() ?? "");
  const [members, setMembers] = useState<FleetMember[]>([]);
  const [draftRoles, setDraftRoles] = useState<Record<number, FleetMember["role"]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingMemberId, setSavingMemberId] = useState<number | null>(null);

  const canLoad = useMemo(() => Boolean(selectedFleet.trim()), [selectedFleet]);

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
        setError("Only fleet admin/owner can manage member roles.");
      } else {
        setError("Unable to load fleet members.");
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
      setMessage(`Updated ${member.phone_number} to ${nextRole}.`);
      await loadMembers();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only fleet admin/owner")) {
        setError("Only fleet admin/owner can change roles.");
      } else if (text.includes("owner")) {
        setError("Owner role can only be changed by owner.");
      } else {
        setError("Could not update member role.");
      }
    } finally {
      setSavingMemberId(null);
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
        <h1>Fleet Members</h1>
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

        <button className="btn btnGhost" type="button" onClick={() => void loadMembers()}>
          {loading ? "Loading..." : "Refresh Members"}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list">
        {members.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No members loaded</div>
              <div className="txSub">Select a fleet and refresh.</div>
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
                  {member.phone_number} | @{member.username} | {member.is_active ? "active" : "inactive"}
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
                  {savingMemberId === member.id ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
