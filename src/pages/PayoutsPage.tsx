import { useEffect, useMemo, useState } from "react";
import {
  bankSimulatorPayouts,
  bogPayouts,
  connectBankSimulator,
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

export default function PayoutsPage() {
  const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
  const [bogItems, setBogItems] = useState<BogPayout[]>([]);
  const [payouts, setPayouts] = useState<BankSimPayout[]>([]);
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
      setMessage(error instanceof Error ? error.message : "Action failed");
    } finally {
      setLoading(false);
    }
  }

  function humanStatus(status: string) {
    if (status === "pending") return "Requested";
    if (status === "processing") return "Processing";
    if (status === "completed") return "Completed";
    if (status === "failed") return "Failed";
    if (status === "accepted") return "Accepted";
    if (status === "settled") return "Completed";
    if (status === "reversed") return "Reversed";
    return status;
  }

  return (
    <section className="card">
      <h1>Payouts</h1>
      <p>Track payout progress clearly for real withdrawals sent through Bank of Georgia. The simulator tools stay below as an operational fallback.</p>

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
                `BoG sync checked ${result.checked_count} open payout(s), updated ${result.updated_count}, errors ${result.error_count}.`
              );
            })
          }
        >
          Refresh all open BoG payouts
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
                  #{item.id} {item.amount} {item.currency}
                </div>
                  <div className="txSub">Driver payout status: {humanStatus(item.status)}</div>
                  <div className="txSub">Destination: {item.bank_account.bank_name} • {item.bank_account.account_number}</div>
                  <div className="txSub">Fleet fee: {Number(item.fee_amount || 0).toFixed(2)} {item.currency}</div>
                  {bogPayout ? <div className="txSub">BoG transfer status: {humanStatus(bogPayout.status)}</div> : <div className="txSub">Not yet sent to BoG</div>}
                  {bogPayout?.failure_reason ? <div className="txSub">Reason: {bogPayout.failure_reason}</div> : null}
                  {bogPayout?.provider_unique_key ? (
                    <div className="txSub">Bank document key: {bogPayout.provider_unique_key}</div>
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
                          setMessage(`Submitted withdrawal #${item.id} to Bank of Georgia.`);
                        })
                      }
                    >
                      Send to BoG
                    </button>
                  ) : (
                    <>
                      <button
                        className="btn btnSoft"
                        type="button"
                        onClick={() =>
                          void run(async () => {
                            await syncBogPayoutStatus(bogPayout.id);
                            setMessage(`Refreshed BoG payout #${bogPayout.id}.`);
                          })
                        }
                      >
                        Refresh status
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
                <div className="txTitle">No withdrawals yet</div>
                <div className="txSub">Driver payout requests will appear here once a withdrawal is submitted.</div>
              </div>
            </div>
        )}
      </div>

      <details className="internalToolsPanel">
        <summary>Internal simulator fallback</summary>
        <p className="txSub internalToolsCopy">
          These controls are for internal payout recovery and testing. Normal owner workflow should use the Bank of Georgia section above.
        </p>
        <div style={{ marginTop: "14px", marginBottom: "14px" }}>
          <button
            className="transferSubmit"
            type="button"
            onClick={() =>
              void run(async () => {
                await connectBankSimulator();
                setMessage("Bank simulator connected.");
              })
            }
          >
            {loading ? "Please wait..." : "Connect Bank Simulator"}
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
                      withdrawal: {item.status}
                      {payout ? ` | simulator: ${payout.status}` : ""}
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
                            setMessage(`Submitted withdrawal #${item.id} to bank simulator.`);
                          })
                        }
                      >
                        Submit
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn btnSoft"
                          type="button"
                          onClick={() =>
                            void run(async () => {
                              await updateBankSimulatorPayoutStatus(payout.id, { status: "processing" });
                              setMessage(`Payout #${payout.id} set to processing.`);
                            })
                          }
                        >
                          Processing
                        </button>
                        <button
                          className="btn btnSoft"
                          type="button"
                          onClick={() =>
                            void run(async () => {
                              await updateBankSimulatorPayoutStatus(payout.id, { status: "settled" });
                              setMessage(`Payout #${payout.id} settled.`);
                            })
                          }
                        >
                          Settled
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
                              setMessage(`Payout #${payout.id} failed.`);
                            })
                          }
                        >
                          Fail
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
                <div className="txTitle">No simulator items</div>
                <div className="txSub">Simulator actions only appear when there are withdrawal requests to replay.</div>
              </div>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
