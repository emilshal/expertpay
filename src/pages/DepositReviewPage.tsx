import { useEffect, useMemo, useState } from "react";
import {
  fleets,
  getActiveFleetName,
  manualMatchIncomingTransfer,
  setActiveFleetName,
  syncDeposits,
  unmatchedIncomingTransfers,
  type Fleet,
  type IncomingBankTransferItem
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function DepositReviewPage() {
  const { pick } = useI18n();
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [selectedFleet, setSelectedFleet] = useState(getActiveFleetName() ?? "");
  const [transfers, setTransfers] = useState<IncomingBankTransferItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingTransferId, setSavingTransferId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [backfillStartDate, setBackfillStartDate] = useState("");
  const [backfillEndDate, setBackfillEndDate] = useState("");

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
      const transferData = await unmatchedIncomingTransfers();
      setTransfers(transferData);
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Only admin/owner")) {
        setError(pick("Only fleet admin/owner can review unmatched deposits.", "დაუდგენელი შევსებების განხილვა მხოლოდ ფლიტის ადმინს ან მფლობელს შეუძლია."));
      } else {
        setError(pick("Unable to load unmatched bank transfers right now.", "დაუდგენელი საბანკო გადარიცხვები ახლა ვერ ჩაიტვირთა."));
      }
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
        pick(
          `Checked ${result.checked_count} item(s), left ${result.unmatched_count} unmatched, credited ${result.credited_count}.`,
          `შემოწმდა ${result.checked_count} ჩანაწერი, დაუდგენელი დარჩა ${result.unmatched_count}, ჩაირიცხა ${result.credited_count}.`
        )
      );
      await loadQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : pick("Bank sync failed.", "საბანკო სინქი ვერ შესრულდა."));
      setLoading(false);
    }
  }

  async function runBackfill() {
    if (!backfillStartDate || !backfillEndDate) {
      setError(pick("Choose both a start date and end date before running a recovery sync.", "აღდგენის სინქამდე აირჩიეთ დაწყების და დასრულების თარიღები."));
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits({ start_date: backfillStartDate, end_date: backfillEndDate });
      setMessage(
        pick(
          `Backfill checked ${result.checked_count} transfer(s) from ${backfillStartDate} to ${backfillEndDate}, matched ${result.matched_count}, credited ${result.credited_count}, and left ${result.unmatched_count} for review.`,
          `Backfill-მა ${backfillStartDate}-დან ${backfillEndDate}-მდე შეამოწმა ${result.checked_count} გადარიცხვა, დაამთხვია ${result.matched_count}, ჩარიცხა ${result.credited_count} და განხილვაში დატოვა ${result.unmatched_count}.`
        )
      );
      await loadQueue();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("Both start_date and end_date")) {
        setError(pick("Choose both a start date and end date before running a recovery sync.", "აღდგენის სინქამდე აირჩიეთ დაწყების და დასრულების თარიღები."));
      } else {
        setError(pick("Backfill failed. Please check the date range and try again.", "Backfill ვერ შესრულდა. შეამოწმეთ თარიღები და სცადეთ თავიდან."));
      }
      setLoading(false);
    }
  }

  async function matchTransfer(transfer: IncomingBankTransferItem) {
    setSavingTransferId(transfer.id);
    setError("");
    setMessage("");
    try {
      await manualMatchIncomingTransfer({
        transfer_id: transfer.id,
        fleet_name: selectedFleet
      });
      setMessage(pick(`Matched ${transfer.amount} ${transfer.currency} to ${selectedFleet}.`, `${transfer.amount} ${transfer.currency} მიება ფლიტს ${selectedFleet}.`));
      await loadQueue();
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      if (text.includes("already finalized")) {
        setError(pick("That transfer was already handled.", "ეს გადარიცხვა უკვე დამუშავდა."));
      } else {
        setError(pick("Could not match this transfer.", "ამ გადარიცხვის მიბმა ვერ მოხერხდა."));
      }
    } finally {
      setSavingTransferId(null);
    }
  }

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>{pick("Deposit Review", "შევსებების განხილვა")}</h1>
        <button className="btn btnGhost" type="button" onClick={() => void refreshBankActivity()}>
          {loading ? pick("Syncing...", "სინქდება...") : pick("Sync from BoG", "BoG-დან სინქი")}
        </button>
      </div>

      <p className="muted">
        {pick(
          "Manual review is used only when a bank transfer arrives without a clean fleet reference code or needs confirmation before reserve crediting.",
          "ხელით განხილვა გამოიყენება მხოლოდ მაშინ, როცა საბანკო გადარიცხვა მოდის მკაფიო ფლიტის კოდის გარეშე ან რეზერვზე ჩარიცხვამდე დამატებითი დადასტურება სჭირდება."
        )}
      </p>

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

        <button className="btn btnGhost" type="button" onClick={() => void loadQueue()}>
          {loading ? pick("Refreshing...", "ახლდება...") : pick("Refresh Queue", "რიგის განახლება")}
        </button>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Recover missed transfers", "გამოტოვებული გადარიცხვების აღდგენა")}</h2>
        </div>
        <p className="muted">{pick("Use a date range backfill when a transfer is missing from the normal BoG activity sync.", "გამოიყენეთ თარიღების დიაპაზონი, როცა გადარიცხვა ჩვეულებრივ BoG სინქში არ ჩანს.")}</p>
        <div className="transferForm">
          <label className="transferField">
            <span className="transferLabel">{pick("Start date", "დაწყების თარიღი")}</span>
            <input
              className="transferInput"
              type="date"
              value={backfillStartDate}
              onChange={(event) => setBackfillStartDate(event.target.value)}
            />
          </label>
          <label className="transferField">
            <span className="transferLabel">{pick("End date", "დასრულების თარიღი")}</span>
            <input
              className="transferInput"
              type="date"
              value={backfillEndDate}
              onChange={(event) => setBackfillEndDate(event.target.value)}
            />
          </label>
          <button className="btn btnGhost" type="button" onClick={() => void runBackfill()}>
            {loading ? pick("Running...", "მუშაობს...") : pick("Run backfill", "Backfill-ის გაშვება")}
          </button>
        </div>
      </div>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="mappingStats">
        <div className="mappingStat">
          <span className="mappingStatValue">{transfers.length}</span>
          <span className="mappingStatLabel">{pick("Awaiting review", "ელოდება განხილვას")}</span>
        </div>
        <div className="mappingStat">
          <span className="mappingStatValue">{selectedFleet || pick("No fleet", "ფლიტი არ არის")}</span>
          <span className="mappingStatLabel">{pick("Current review scope", "მიმდინარე განხილვის არე")}</span>
        </div>
      </div>

      <div className="txList" role="list">
        {transfers.length === 0 ? (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("No unmatched transfers", "დაუდგენელი გადარიცხვები არ არის")}</div>
              <div className="txSub">{pick("Incoming transfers with missing or incorrect references will appear here.", "აქ გამოჩნდება შემოსული გადარიცხვები, რომლებსაც კოდი აკლიათ ან არასწორი კოდით მოვიდა.")}</div>
            </div>
          </div>
        ) : (
          transfers.map((transfer) => (
            <div className="txRow txRowStacked" role="listitem" key={transfer.id}>
              <div className="txMain">
                <div className="txTitle">
                  {transfer.amount} {transfer.currency}
                </div>
                <div className="txSub">{transfer.payer_name || pick("Unknown payer", "უცნობი გადამხდელი")}</div>
                <div className="txSub">{pick("Bank comment", "ბანკის კომენტარი")}: {transfer.reference_text || pick("No reference provided", "კოდი არ არის მითითებული")}</div>
                <div className="txSub">
                  {pick("Source", "წყარო")}: {transfer.sync_source === "backfill" ? pick("Recovered by backfill", "აღმოჩენილია backfill-ით") : pick("Normal bank sync", "ჩვეულებრივი საბანკო სინქი")}
                </div>
                <div className="txSub">
                  {transfer.booking_date || transfer.value_date || transfer.created_at}
                </div>
              </div>

              <div className="reviewMatchControls">
                <button
                  className="btn btnPrimary"
                  type="button"
                  onClick={() => void matchTransfer(transfer)}
                  disabled={savingTransferId === transfer.id || !selectedFleet}
                >
                  {savingTransferId === transfer.id ? pick("Crediting...", "ირიცხება...") : pick("Credit to fleet reserve", "ფლიტის რეზერვზე ჩარიცხვა")}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
