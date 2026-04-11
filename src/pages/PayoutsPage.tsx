import { useEffect, useMemo, useState } from "react";
import {
  bankSimulatorPayouts,
  bogPayouts,
  connectBankSimulator,
  requestBogPayoutOtp,
  signBogPayout,
  submitBogPayout,
  submitBankSimulatorPayout,
  syncAllBogPayoutStatuses,
  syncBogPayoutStatus,
  updateBankSimulatorPayoutStatus,
  withdrawalsList,
  type BogPayout,
  type BankSimPayout,
  type WithdrawalItem
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function PayoutsPage() {
  const { pick, locale } = useI18n();
  const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
  const [bogItems, setBogItems] = useState<BogPayout[]>([]);
  const [payouts, setPayouts] = useState<BankSimPayout[]>([]);
  const [otpValues, setOtpValues] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const bogByWithdrawal = useMemo(() => {
    return new Map(bogItems.map((payout) => [payout.withdrawal_id, payout]));
  }, [bogItems]);

  const payoutByWithdrawal = useMemo(() => {
    return new Map(payouts.map((payout) => [payout.withdrawal_id, payout]));
  }, [payouts]);

  async function refresh() {
    const [withdrawalData, bogData, payoutData] = await Promise.all([
      withdrawalsList(),
      bogPayouts(),
      bankSimulatorPayouts()
    ]);
    setWithdrawals(withdrawalData);
    setBogItems(bogData);
    setPayouts(payoutData);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function run(action: () => Promise<void>) {
    setLoading(true);
    setMessage("");
    try {
      await action();
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : pick("Action failed", "ქმედება ვერ შესრულდა"));
    } finally {
      setLoading(false);
    }
  }

  function humanStatus(status: string) {
    if (status === "pending") return pick("Requested", "მოთხოვნილია");
    if (status === "processing") return pick("Processing", "მუშავდება");
    if (status === "completed") return pick("Completed", "დასრულდა");
    if (status === "failed") return pick("Failed", "ვერ შესრულდა");
    if (status === "accepted") return pick("Accepted", "მიღებულია");
    if (status === "settled") return pick("Completed", "დასრულდა");
    if (status === "reversed") return pick("Reversed", "შებრუნებულია");
    return status;
  }

  function humanBogProviderStatus(status: string) {
    if (status === "A") return pick("Waiting for signature", "ხელმოწერას ელოდება");
    if (status === "N") return pick("Created at bank, still incomplete", "ბანკში შექმნილია, მაგრამ ჯერ დაუსრულებელია");
    if (status === "S") return pick("Signed", "ხელმოწერილია");
    if (status === "T") return pick("In progress at bank", "ბანკში დამუშავების პროცესშია");
    if (status === "Z") return pick("Signing in progress", "ხელმოწერის პროცესი მიმდინარეობს");
    if (status === "P") return pick("Completed at bank", "ბანკში დასრულებულია");
    if (status === "R") return pick("Rejected by bank", "ბანკმა უარყო");
    if (status === "D") return pick("Cancelled by bank", "ბანკმა გააუქმა");
    if (status === "C") return pick("Cancelled by response", "პასუხით გაუქმებულია");
    return status || pick("Pending bank status", "ბანკის სტატუსს ელოდება");
  }

  function formatTransactionDate(value: string) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const dateLocale = locale.startsWith("ka") ? "ka-GE" : "en-GB";
    return new Intl.DateTimeFormat(dateLocale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).format(date);
  }

  return (
    <section className="card">
      <h1>{pick("Payouts", "გატანები")}</h1>
      <p>{pick("Track payout progress clearly for real withdrawals sent through Bank of Georgia. The simulator tools stay below as an operational fallback.", "თვალი ადევნეთ რეალური გატანების პროგრესს, რომლებიც Bank of Georgia-ს გავლით იგზავნება. სიმულატორის ინსტრუმენტები ქვემოთ რჩება როგორც შიდა ალტერნატივა.")}</p>

      {message ? <p className="statusHint">{message}</p> : null}

      <h2 className="h2" style={{ marginBottom: "10px", marginTop: "14px" }}>
        Bank of Georgia
      </h2>
      <div style={{ marginTop: "10px", marginBottom: "14px" }}>
        <button
          className="btn btnSoft"
          type="button"
          onClick={() =>
            void run(async () => {
              const result = await syncAllBogPayoutStatuses();
              setMessage(
                pick(
                  `BoG sync checked ${result.checked_count} open payout(s), updated ${result.updated_count}, errors ${result.error_count}.`,
                  `BoG სინქმა შეამოწმა ${result.checked_count} ღია გატანა, განაახლა ${result.updated_count}, შეცდომები ${result.error_count}.`
                )
              );
            })
          }
        >
          {pick("Refresh all open BoG payouts", "ყველა ღია BoG გატანის განახლება")}
        </button>
      </div>
      <div className="txList" role="list">
        {withdrawals.length ? (
          withdrawals.map((item) => {
            const bogPayout = bogByWithdrawal.get(item.id);
            const payout = payoutByWithdrawal.get(item.id);
            return (
              <div key={item.id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">
                    {pick("Transaction", "ტრანზაქცია")} #{item.id}
                  </div>
                  <div className="txSub">{item.driver_name}</div>
                  <div className="txSub">{formatTransactionDate(item.created_at)}</div>
                  <div className="txSub">{pick("Amount", "თანხა")}: {item.amount} {item.currency}</div>
                  <div className="txSub">{pick("Driver payout status", "მძღოლის გატანის სტატუსი")}: {humanStatus(item.status)}</div>
                  <div className="txSub">{pick("Driver fee", "მძღოლის საკომისიო")}: {Number(item.fee_amount || 0).toFixed(2)} {item.currency}</div>
                  {bogPayout ? <div className="txSub">{pick("BoG transfer status", "BoG გადარიცხვის სტატუსი")}: {humanStatus(bogPayout.status)}</div> : <div className="txSub">{pick("Not yet sent to BoG", "BoG-ში ჯერ არ გაგზავნილა")}</div>}
                  {bogPayout?.provider_status ? (
                    <div className="txSub">{pick("BoG document state", "BoG დოკუმენტის სტატუსი")}: {humanBogProviderStatus(bogPayout.provider_status)}</div>
                  ) : null}
                  {bogPayout?.failure_reason ? <div className="txSub">{pick("Reason", "მიზეზი")}: {bogPayout.failure_reason}</div> : null}
                  {bogPayout?.provider_unique_key ? (
                    <div className="txSub">{pick("Bank document key", "ბანკის დოკუმენტის კოდი")}: {bogPayout.provider_unique_key}</div>
                  ) : null}
                </div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
                  {!bogPayout ? (
                    <button
                      className="btn btnSoft"
                      type="button"
                      onClick={() =>
                        void run(async () => {
                          await submitBogPayout(item.id);
                          setMessage(pick(`Submitted withdrawal #${item.id} to Bank of Georgia.`, `გატანა #${item.id} გაგზავნილია Bank of Georgia-ში.`));
                        })
                      }
                    >
                      {pick("Send to BoG", "BoG-ში გაგზავნა")}
                    </button>
                  ) : (
                    <>
                      <button
                        className="btn btnSoft"
                        type="button"
                        onClick={() =>
                          void run(async () => {
                            await syncBogPayoutStatus(bogPayout.id);
                            setMessage(pick(`Refreshed BoG payout #${bogPayout.id}.`, `BoG გატანა #${bogPayout.id} განახლდა.`));
                          })
                        }
                      >
                        {pick("Refresh status", "სტატუსის განახლება")}
                      </button>
                      {bogPayout.status === "processing" ? (
                        <>
                          <button
                            className="btn btnSoft"
                            type="button"
                            onClick={() =>
                              void run(async () => {
                                const result = await requestBogPayoutOtp(bogPayout.id);
                                setMessage(result.detail);
                              })
                            }
                          >
                            {pick("Request OTP", "OTP-ის მოთხოვნა")}
                          </button>
                          <input
                            type="text"
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            placeholder={pick("OTP code", "OTP კოდი")}
                            value={otpValues[bogPayout.id] ?? ""}
                            onChange={(event) =>
                              setOtpValues((current) => ({
                                ...current,
                                [bogPayout.id]: event.target.value
                              }))
                            }
                            style={{ minWidth: "110px" }}
                          />
                          <button
                            className="btn btnSoft"
                            type="button"
                            onClick={() =>
                              void run(async () => {
                                const otp = (otpValues[bogPayout.id] ?? "").trim();
                                if (!otp) {
                                  throw new Error(pick("Enter the OTP code from Bank of Georgia first.", "ჯერ შეიყვანეთ Bank of Georgia-ს OTP კოდი."));
                                }
                                const result = await signBogPayout(bogPayout.id, otp);
                                setOtpValues((current) => ({ ...current, [bogPayout.id]: "" }));
                                setMessage(result.detail);
                              })
                            }
                          >
                            {pick("Sign payout", "გატანის ხელმოწერა")}
                          </button>
                        </>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            );
          })
        ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("No withdrawals yet", "გატანის მოთხოვნები ჯერ არ არის")}</div>
                <div className="txSub">{pick("Driver payout requests will appear here once a withdrawal is submitted.", "მძღოლის გატანის მოთხოვნები აქ გამოჩნდება, როცა გატანა შეიქმნება.")}</div>
              </div>
            </div>
        )}
      </div>

      <details className="internalToolsPanel">
        <summary>{pick("Internal simulator fallback", "შიდა სიმულატორის ალტერნატივა")}</summary>
        <p className="txSub internalToolsCopy">
          {pick("These controls are for internal payout recovery and testing. Normal owner workflow should use the Bank of Georgia section above.", "ეს კონტროლები განკუთვნილია შიდა აღდგენისა და ტესტირებისთვის. ნორმალურ მფლობელის პროცესში გამოიყენეთ ზემოთ მოცემული Bank of Georgia-ს სექცია.")}
        </p>
        <div style={{ marginTop: "14px", marginBottom: "14px" }}>
          <button
            className="transferSubmit"
            type="button"
            onClick={() =>
              void run(async () => {
                await connectBankSimulator();
                setMessage(pick("Bank simulator connected.", "ბანკის სიმულატორი დაკავშირებულია."));
              })
            }
          >
            {loading ? pick("Please wait...", "გთხოვთ დაელოდოთ...") : pick("Connect Bank Simulator", "ბანკის სიმულატორის დაკავშირება")}
          </button>
        </div>
        <div className="txList" role="list">
          {withdrawals.length ? (
            withdrawals.map((item) => {
              const payout = payoutByWithdrawal.get(item.id);
              return (
                <div key={`sim-${item.id}`} className="txRow" role="listitem">
                  <div className="txMain">
                    <div className="txTitle">
                      #{item.id} {item.amount} {item.currency}
                    </div>
                    <div className="txSub">
                      {pick("withdrawal", "გატანა")}: {item.status}
                      {payout ? ` | ${pick("simulator", "სიმულატორი")}: ${payout.status}` : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {!payout ? (
                      <button
                        className="btn btnSoft"
                        type="button"
                        onClick={() =>
                          void run(async () => {
                            await submitBankSimulatorPayout(item.id);
                            setMessage(pick(`Submitted withdrawal #${item.id} to bank simulator.`, `გატანა #${item.id} გაგზავნილია ბანკის სიმულატორში.`));
                          })
                        }
                      >
                        {pick("Submit", "გაგზავნა")}
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn btnSoft"
                          type="button"
                          onClick={() =>
                            void run(async () => {
                              await updateBankSimulatorPayoutStatus(payout.id, { status: "processing" });
                              setMessage(pick(`Payout #${payout.id} set to processing.`, `გატანა #${payout.id} გადავიდა processing-ში.`));
                            })
                          }
                        >
                          {pick("Processing", "მუშავდება")}
                        </button>
                        <button
                          className="btn btnSoft"
                          type="button"
                          onClick={() =>
                            void run(async () => {
                              await updateBankSimulatorPayoutStatus(payout.id, { status: "settled" });
                              setMessage(pick(`Payout #${payout.id} settled.`, `გატანა #${payout.id} დასრულდა.`));
                            })
                          }
                        >
                          {pick("Settled", "დასრულდა")}
                        </button>
                        <button
                          className="btn btnSoft"
                          type="button"
                          onClick={() =>
                            void run(async () => {
                              await updateBankSimulatorPayoutStatus(payout.id, {
                                status: "failed",
                                failure_reason: "simulated failure"
                              });
                              setMessage(pick(`Payout #${payout.id} failed.`, `გატანა #${payout.id} ჩავარდა.`));
                            })
                          }
                        >
                          {pick("Fail", "ჩავარდნა")}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{pick("No simulator items", "სიმულატორის ჩანაწერები არ არის")}</div>
                <div className="txSub">{pick("Simulator actions only appear when there are withdrawal requests to replay.", "სიმულატორის ქმედებები გამოჩნდება მხოლოდ მაშინ, როცა გასამეორებელი გატანის მოთხოვნები არსებობს.")}</div>
              </div>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
