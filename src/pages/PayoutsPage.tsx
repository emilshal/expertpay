import { useEffect, useMemo, useState } from "react";
import {
  bankSimulatorPayouts,
  connectBankSimulator,
  submitBankSimulatorPayout,
  updateBankSimulatorPayoutStatus,
  withdrawalsList,
  type BankSimPayout,
  type WithdrawalItem
} from "../lib/api";

export default function PayoutsPage() {
  const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
  const [payouts, setPayouts] = useState<BankSimPayout[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const payoutByWithdrawal = useMemo(() => {
    return new Map(payouts.map((payout) => [payout.withdrawal_id, payout]));
  }, [payouts]);

  async function refresh() {
    const [withdrawalData, payoutData] = await Promise.all([withdrawalsList(), bankSimulatorPayouts()]);
    setWithdrawals(withdrawalData);
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

  return (
    <section className="card">
      <h1>Payouts Simulator</h1>
      <p>Phase 2 bank-simulator lifecycle for withdrawals.</p>

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

      {message ? <p className="statusHint">{message}</p> : null}

      <h2 className="h2" style={{ marginBottom: "10px", marginTop: "14px" }}>
        Withdrawals
      </h2>
      <div className="txList" role="list">
        {withdrawals.length ? (
          withdrawals.map((item) => {
            const payout = payoutByWithdrawal.get(item.id);
            return (
              <div key={item.id} className="txRow" role="listitem">
                <div className="txMain">
                  <div className="txTitle">
                    #{item.id} {item.amount} {item.currency}
                  </div>
                  <div className="txSub">
                    withdrawal: {item.status}
                    {payout ? ` | payout: ${payout.status}` : ""}
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
              <div className="txTitle">No withdrawals yet</div>
              <div className="txSub">Create one from Dashboard withdraw modal first.</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
