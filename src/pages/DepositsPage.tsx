import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  depositInstructions,
  depositsList,
  type DepositInstruction,
  type DepositItem
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function DepositsPage() {
  const { pick } = useI18n();
  const navigate = useNavigate();
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
    <section className="card reservePage">
      <button className="reserveBackButton" type="button" onClick={() => navigate("/dashboard")} aria-label={pick("Back to dashboard", "დეშბორდზე დაბრუნება")}>
        <span aria-hidden="true">←</span>
      </button>

      <div className="reserveHero">
        <div>
          <p className="reserveEyebrow">{pick("Fleet reserve", "ფლიტის რეზერვი")}</p>
          <h1>{pick("Add money to your reserve", "რეზერვის შევსება")}</h1>
          <p className="muted">
            {pick(
              "Make one bank transfer and write your fleet code in the comment. We will add the money to your reserve after it arrives.",
              "გააკეთეთ ერთი საბანკო გადარიცხვა და კომენტარში ჩაწერეთ თქვენი ფლიტის კოდი. თანხა რეზერვზე აისახება მიღების შემდეგ."
            )}
          </p>
        </div>
      </div>

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
        <div className="reserveSteps" role="list">
          <div className="reserveStep" role="listitem">
            <div className="reserveStepNumber">1</div>
            <div className="reserveStepBody">
              <div className="txTitle">{pick("Send money to this account", "გადარიცხეთ თანხა ამ ანგარიშზე")}</div>
              <div className="txSub">{instructions.bank_name}</div>
              <div className="txSub">{instructions.account_holder_name || pick("Company account", "კომპანიის ანგარიში")}</div>
              <div className="reserveCopyBox">
                <span>{instructions.account_number}</span>
                <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.account_number)}>
                  {pick("Copy", "კოპირება")}
                </button>
              </div>
            </div>
          </div>

          <div className="reserveStep reserveStepImportant" role="listitem">
            <div className="reserveStepNumber">2</div>
            <div className="reserveStepBody">
              <div className="txTitle">{pick("Write this code in the transfer comment", "გადარიცხვის კომენტარში ჩაწერეთ ეს კოდი")}</div>
              <div className="reserveCopyBox reserveCodeBox">
                <span className="mappingCode">{instructions.reference_code}</span>
                <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.reference_code)}>
                  {pick("Copy", "კოპირება")}
                </button>
              </div>
              <div className="txSub">
                {pick(
                  "This is how we know the money belongs to your fleet.",
                  "ამით ვხვდებით, რომ თანხა თქვენს ფლიტს ეკუთვნის."
                )}
              </div>
            </div>
          </div>

          <div className="reserveStep" role="listitem">
            <div className="reserveStepNumber">3</div>
            <div className="reserveStepBody">
              <div className="txTitle">{pick("You are done", "მზად არის")}</div>
              <div className="txSub">
                {pick(
                  "Your reserve updates after the transfer arrives. If the code is missing, our team can still review it manually.",
                  "რეზერვი განახლდება თანხის მიღების შემდეგ. თუ კოდი გამოგრჩათ, ჩვენი გუნდი მაინც შეძლებს ხელით შემოწმებას."
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <h2 className="h2" style={{ marginTop: "22px", marginBottom: "10px" }}>
        {pick("Recent reserve top-ups", "ბოლო რეზერვის შევსებები")}
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
              <div className="txTitle">{loading ? pick("Loading...", "იტვირთება...") : pick("No top-ups yet", "შევსებები ჯერ არ არის")}</div>
              <div className="txSub">{pick("Reserve top-ups will appear here after money is added to your fleet.", "რეზერვის შევსებები აქ გამოჩნდება, როცა თანხა თქვენს ფლიტს დაემატება.")}</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
