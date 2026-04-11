import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  depositInstructions,
  syncDeposits,
  type DepositInstruction
} from "../lib/api";
import { useI18n } from "../lib/i18n";

function parseApiError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  const raw = error.message?.trim();
  if (!raw) return fallback;

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }

  return raw;
}

export default function OperatorDashboardPage() {
  const { pick } = useI18n();
  const [instructions, setInstructions] = useState<DepositInstruction | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const instructionData = await depositInstructions();
      setInstructions(instructionData);
    } catch (err) {
      setError(parseApiError(err, pick("Unable to load operator tools right now.", "ოპერატორის ინსტრუმენტები ახლა ვერ ჩაიტვირთა.")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function runDepositSync() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await syncDeposits();
      setMessage(
        pick(
          `Checked ${result.checked_count} bank activity item(s), matched ${result.matched_count}, and credited ${result.credited_count} deposit(s).`,
          `შემოწმდა ${result.checked_count} საბანკო ჩანაწერი, დაემთხვა ${result.matched_count} და ჩაირიცხა ${result.credited_count} შევსება.`
        )
      );
    } catch (err) {
      setError(parseApiError(err, pick("Deposit sync failed.", "შევსების სინქი ვერ შესრულდა.")));
    } finally {
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

  return (
    <div className="ownerDashboard">
      <section className="card ownerHero">
        <div className="ownerHeroEyebrow">{pick("Operator tools", "ოპერატორის ინსტრუმენტები")}</div>
        <div className="ownerHeroBalance">{pick("BoG sync access", "BoG სინქის წვდომა")}</div>
        <p className="ownerHeroNote">
          {pick(
            "Use this page for day-to-day payout and funding operations. Admin-only reporting and review pages stay hidden unless your role allows them.",
            "ეს გვერდი გამოიყენეთ ყოველდღიური გატანისა და შევსების ოპერაციებისთვის. მხოლოდ ადმინის გვერდები დამალული დარჩება, თუ თქვენი როლი ამის საშუალებას არ იძლევა."
          )}
        </p>
        <div className="ownerHeroMeta">
          <span>{instructions?.fleet_name ?? pick("Active fleet", "აქტიური ფლიტი")}</span>
          {loading ? <span>{pick("Refreshing...", "ახლდება...")}</span> : <span>{pick("Operator role", "ოპერატორის როლი")}</span>}
        </div>
      </section>

      {error ? <p className="statusError">{error}</p> : null}
      {message ? <p className="statusHint">{message}</p> : null}

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">{pick("Fleet funding instructions", "ფლიტის შევსების ინსტრუქცია")}</h2>
          <button className="btn btnGhost" type="button" onClick={() => void runDepositSync()}>
            {loading ? pick("Syncing...", "სინქდება...") : pick("Sync from BoG", "BoG-დან სინქი")}
          </button>
        </div>

        {instructions ? (
          <div className="txList" role="list">
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("Use this exact fleet reference", "გამოიყენეთ ზუსტად ეს ფლიტის კოდი")}</div>
                <div className="txSub mappingCode">{instructions.reference_code}</div>
                <div className="txSub">{pick("This code must be included in the bank transfer comment so the deposit can be matched.", "შევსების დასამთხვევად ეს კოდი აუცილებლად უნდა იყოს საბანკო გადარიცხვის კომენტარში.")}</div>
              </div>
              <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.reference_code)}>
                {pick("Copy", "კოპირება")}
              </button>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("Company account", "კომპანიის ანგარიში")}</div>
                <div className="txSub">{instructions.account_holder_name || pick("Company account", "კომპანიის ანგარიში")}</div>
                <div className="txSub">{instructions.account_number}</div>
              </div>
              <button className="btn btnSoft" type="button" onClick={() => void copyValue(instructions.account_number)}>
                {pick("Copy", "კოპირება")}
              </button>
            </div>
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("What happens next", "შემდეგ რა ხდება")}</div>
                <div className="txSub">{pick("After the next BoG sync, matched funding will be credited to the fleet reserve automatically.", "შემდეგი BoG სინქის შემდეგ დამთხვევილი თანხა ავტომატურად ჩაირიცხება ფლიტის რეზერვზე.")}</div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="ownerQuickLinks">
        <Link className="card ownerLinkCard" to="/payouts">
          <div className="ownerLinkEyebrow">{pick("Payouts", "გატანები")}</div>
          <div className="txTitle">{pick("Track payout progress", "გატანის პროგრესის ნახვა")}</div>
          <div className="txSub">{pick("Refresh Bank of Georgia payout statuses and follow any in-flight withdrawal requests.", "განაახლეთ Bank of Georgia-ს გატანის სტატუსები და თვალი ადევნეთ მიმდინარე მოთხოვნებს.")}</div>
        </Link>
      </section>
    </div>
  );
}
