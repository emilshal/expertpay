import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  depositInstructions,
  depositsList,
  getActiveRole,
  syncDeposits,
  type DepositInstruction,
  type DepositItem
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function DepositsPage() {
  const { pick } = useI18n();
  const navigate = useNavigate();
  const role = getActiveRole();
  const isOwnerAdmin = role === "owner" || role === "admin";
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [deposits, setDeposits] = useState<DepositItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [instructionData, depositData] = await Promise.all([depositInstructions(), depositsList()]);
      setInstructions(instructionData);
      setDeposits(depositData);
    } catch {
      setError(pick("Unable to load deposit details right now.", "შევსების დეტალები ახლა ვერ ჩაიტვირთა."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function runSync() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits();
      setMessage(
        pick(
          `Checked ${result.checked_count} bank activity item(s), matched ${result.matched_count}, credited ${result.credited_count} for ${result.credited_total} GEL.`,
          `შემოწმდა ${result.checked_count} საბანკო ჩანაწერი, დაემთხვა ${result.matched_count}, ჩაირიცხა ${result.credited_count} ჩანაწერი ${result.credited_total} GEL-ზე.`
        )
      );
      await loadData();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : pick("Deposit sync failed.", "შევსების სინქი ვერ შესრულდა."));
      setLoading(false);
    }
  }

  async function copyValue(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage(pick("Copied.", "კოპირებულია."));
    } catch {
      setMessage(pick("Copy failed.", "კოპირება ვერ მოხერხდა."));
    }
  }

  const creditedTotal = deposits.reduce((sum, item) => sum + Number(item.amount || 0), 0);

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>{pick("Deposits", "შევსებები")}</h1>
        <div className="toolbarRow">
          <button className="btn btnGhost" type="button" onClick={() => navigate("/card-topup")}>
            {pick("Card top-up", "ბარათით შევსება")}
          </button>
          {isOwnerAdmin ? (
            <button className="btn btnGhost" type="button" onClick={() => navigate("/deposit-review")}>
              {pick("Review Queue", "განხილვის რიგი")}
            </button>
          ) : null}
          <button className="btn btnGhost" type="button" onClick={() => void runSync()}>
            {loading ? pick("Syncing...", "სინქდება...") : pick("Sync from BoG", "BoG-დან სინქი")}
          </button>
        </div>
      </div>

      <p className="muted">
        {pick(
          "Fund your fleet reserve by bank transfer. Use the exact fleet reference code below so ExpertPay can match the money to your fleet after the next BoG sync.",
          "შეავსეთ ფლიტის რეზერვი საბანკო გადარიცხვით. გამოიყენეთ ქვემოთ მოცემული ზუსტი ფლიტის კოდი, რომ ExpertPay-მ შემდეგ BoG სინქზე თანხა სწორ ფლიტს მიაბას."
        )}
      </p>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <div className="mappingStats">
        <div className="mappingStat">
          <span className="mappingStatValue">{Number(creditedTotal || 0).toFixed(2)} GEL</span>
          <span className="mappingStatLabel">{pick("Credited so far", "ჩარიცხულია სულ")}</span>
        </div>
        <div className="mappingStat">
          <span className="mappingStatValue">{deposits.length}</span>
          <span className="mappingStatLabel">{pick("Matched deposits", "დამთხვევილი შევსებები")}</span>
        </div>
      </div>

      {instructions ? (
        <div className="txList" role="list" style={{ marginTop: "14px" }}>
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Step 1: Send to this bank", "ნაბიჯი 1: ჩარიცხეთ ამ ბანკში")}</div>
              <div className="txSub">{instructions.bank_name}</div>
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Company account holder", "კომპანიის ანგარიშის მფლობელი")}</div>
              <div className="txSub">{instructions.account_holder_name || pick("Company account", "კომპანიის ანგარიში")}</div>
            </div>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Destination account number", "მიმღების ანგარიშის ნომერი")}</div>
              <div className="txSub">{instructions.account_number}</div>
            </div>
            <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.account_number)}>
              {pick("Copy", "კოპირება")}
            </button>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Step 2: Put this exact fleet reference in the transfer comment", "ნაბიჯი 2: გადარიცხვის კომენტარში ჩაწერეთ ზუსტად ეს ფლიტის კოდი")}</div>
              <div className="txSub mappingCode">{instructions.reference_code}</div>
              <div className="txSub">{pick("Without this code, the transfer may wait in manual review before your reserve is credited.", "ამ კოდის გარეშე გადარიცხვა შეიძლება ხელით განხილვაში დარჩეს, სანამ რეზერვზე ჩაირიცხება.")}</div>
            </div>
            <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.reference_code)}>
              {pick("Copy", "კოპირება")}
            </button>
          </div>

          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("Step 3: Wait for BoG sync and matching", "ნაბიჯი 3: დაელოდეთ BoG-ის სინქსა და დამთხვევას")}</div>
              <div className="txSub">
                {pick("Your fleet reserve updates after ExpertPay syncs incoming BoG activity and matches the transfer to this reference.", "ფლიტის რეზერვი განახლდება მას შემდეგ, რაც ExpertPay შემოსულ BoG აქტივობას სინქავს და ამ კოდს გადარიცხვას მიაბამს.")}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <h2 className="h2" style={{ marginTop: "22px", marginBottom: "10px" }}>
        {pick("Recent deposits", "ბოლო შევსებები")}
      </h2>
      <div className="txList" role="list">
        {deposits.length ? (
          deposits.map((deposit) => (
            <div key={deposit.id} className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">
                  {deposit.amount} {deposit.currency}
                </div>
                <div className="txSub">{deposit.payer_name || deposit.reference_code}</div>
                <div className="txSub">{pick("Reference", "კოდი")} {deposit.reference_code}</div>
                <div className="txSub">{deposit.completed_at}</div>
              </div>
              <div className="txAmount pos">{pick("Credited", "ჩარიცხულია")}</div>
            </div>
          ))
        ) : (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("No deposits yet", "შევსებები ჯერ არ არის")}</div>
              <div className="txSub">{pick("Matched bank transfers will appear here once your fleet reserve is credited.", "დამთხვევილი საბანკო გადარიცხვები აქ გამოჩნდება, როცა ფლიტის რეზერვზე ჩაირიცხება.")}</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
