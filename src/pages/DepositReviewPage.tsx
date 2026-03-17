import { useEffect, useMemo, useState } from "react";
import {
  fleets,
  fleetMembers,
  getActiveFleetName,
  manualMatchIncomingTransfer,
  setActiveFleetName,
  syncDeposits,
  unmatchedIncomingTransfers,
  type Fleet,
  type FleetMember,
  type IncomingBankTransferItem
} from "../lib/api";

export default function DepositReviewPage() {
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [selectedFleet, setSelectedFleet] = useState(getActiveFleetName() ?? "");
  const [members, setMembers] = useState<FleetMember[]>([]);
  const [transfers, setTransfers] = useState<IncomingBankTransferItem[]>([]);
  const [draftMatches, setDraftMatches] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [savingTransferId, setSavingTransferId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const canLoad = useMemo(() => Boolean(selectedFleet.trim()), [selectedFleet]);

  async function loadFleets() {
    const data = await fleets();
    setFleetList(data);
    if (!selectedFleet && data.length > 0) {
      setSelectedFleet(data[0].name);
      setActiveFleetName(data[0].name);
    }
  }

  async function loadQueue() {
    if (!canLoad) return;
    setLoading(true);
    setError("");
    try {
      const [memberData, transferData] = await Promise.all([
        fleetMembers(selectedFleet),
        unmatchedIncomingTransfers()
      ]);
      setMembers(memberData);
      setTransfers(transferData);
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only admin/owner")) {
        setError("Only fleet admin/owner can review unmatched deposits.");
      } else {
        setError("Unable to load unmatched bank transfers right now.");
      }
      setMembers([]);
      setTransfers([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadFleets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedFleet) {
      void loadQueue();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFleet]);

  async function refreshBankActivity() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits();
      setMessage(
        `Checked ${result.checked_count} item(s), left ${result.unmatched_count} unmatched, credited ${result.credited_count}.`
      );
      await loadQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bank sync failed.");
      setLoading(false);
    }
  }

  async function matchTransfer(transfer: IncomingBankTransferItem) {
    const phoneNumber = draftMatches[transfer.id];
    if (!phoneNumber) return;

    setSavingTransferId(transfer.id);
    setError("");
    setMessage("");
    try {
      await manualMatchIncomingTransfer({
        transfer_id: transfer.id,
        phone_number: phoneNumber
      });
      setMessage(`Matched ${transfer.amount} ${transfer.currency} to ${phoneNumber}.`);
      setDraftMatches((prev) => {
        const next = { ...prev };
        delete next[transfer.id];
        return next;
      });
      await loadQueue();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Phone number was not found")) {
        setError("That phone number is not in the selected fleet.");
      } else if (text.includes("already finalized")) {
        setError("That transfer was already handled.");
      } else {
        setError("Could not match this transfer.");
      }
    } finally {
      setSavingTransferId(null);
    }
  }

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>Deposit Review</h1>
        <button className="btn btnGhost" type="button" onClick={() => void refreshBankActivity()}>
          {loading ? "Syncing..." : "Sync from BoG"}
        </button>
      </div>

      <p className="muted">
        Manual review is the safety net for incoming bank transfers that arrive without a clean ExpertPay reference.
      </p>

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

        <button className="btn btnGhost" type="button" onClick={() => void loadQueue()}>
          {loading ? "Refreshing..." : "Refresh Queue"}
        </button>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="txList" role="list">
        {transfers.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No unmatched transfers</div>
              <div className="txSub">Incoming transfers with missing or incorrect references will appear here.</div>
            </div>
          </div>
        ) : (
          transfers.map((transfer) => (
            <div className="txRow txRowStacked" role="listitem" key={transfer.id}>
              <div className="txMain">
                <div className="txTitle">
                  {transfer.amount} {transfer.currency}
                </div>
                <div className="txSub">{transfer.payer_name || "Unknown payer"}</div>
                <div className="txSub">Reference: {transfer.reference_text || "No reference provided"}</div>
                <div className="txSub">
                  {transfer.booking_date || transfer.value_date || transfer.created_at}
                </div>
              </div>

              <div className="reviewMatchControls">
                <span className="transferSelectWrap reviewMatchSelect">
                  <select
                    className="transferInput"
                    value={draftMatches[transfer.id] ?? ""}
                    onChange={(event) =>
                      setDraftMatches((prev) => ({
                        ...prev,
                        [transfer.id]: event.target.value
                      }))
                    }
                  >
                    <option value="">Choose fleet member</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.phone_number}>
                        {(member.first_name || member.last_name
                          ? `${member.first_name} ${member.last_name}`.trim()
                          : member.username) + ` • ${member.phone_number}`}
                      </option>
                    ))}
                  </select>
                </span>

                <button
                  className="btn btnPrimary"
                  type="button"
                  onClick={() => void matchTransfer(transfer)}
                  disabled={savingTransferId === transfer.id || !draftMatches[transfer.id]}
                >
                  {savingTransferId === transfer.id ? "Matching..." : "Match Deposit"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
