import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  bogCardOrders,
  createBogCardOrder,
  syncBogCardOrder,
  type BogCardOrder
} from "../lib/api";

export default function CardTopupPage() {
  const navigate = useNavigate();
  const [amount, setAmount] = useState("25.00");
  const [orders, setOrders] = useState<BogCardOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadOrders() {
    setLoading(true);
    setError("");
    try {
      const rows = await bogCardOrders();
      setOrders(rows);
    } catch {
      setError("Unable to load card top-up orders right now.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadOrders();
  }, []);

  async function startCheckout() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const order = await createBogCardOrder({ amount, currency: "GEL", save_card: false });
      setMessage("Secure Bank of Georgia checkout created. Redirecting now...");
      await loadOrders();
      if (order.redirect_url) {
        window.location.assign(order.redirect_url);
        return;
      }
      setError("BoG returned an order but no redirect URL.");
    } catch (checkoutError) {
      setError(checkoutError instanceof Error ? checkoutError.message : "Unable to start card payment.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshOrder(providerOrderId: string) {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const order = await syncBogCardOrder(providerOrderId);
      setMessage(`Order ${order.provider_order_id} is now ${order.status}.`);
      await loadOrders();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "Unable to refresh card order.");
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>Card top-up</h1>
        <div className="toolbarRow">
          <button className="btn btnGhost" type="button" onClick={() => navigate("/deposits")}>
            Bank transfer
          </button>
          <button className="btn btnGhost" type="button" onClick={() => void loadOrders()}>
            Refresh list
          </button>
        </div>
      </div>

      <p className="muted">
        Pay with your card through Bank of Georgia&apos;s hosted checkout. After payment, return here and refresh the
        order status if it has not updated yet.
      </p>

      {error ? <p className="statusError" style={{ marginTop: "12px" }}>{error}</p> : null}
      {message ? <p className="statusHint" style={{ marginTop: "12px" }}>{message}</p> : null}

      <div className="cardTopupForm">
        <label className="cardTopupField">
          <span className="txSub">Amount (GEL)</span>
          <input
            className="transferInput"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="25.00"
          />
        </label>
        <button className="transferSubmit" type="button" onClick={() => void startCheckout()} disabled={loading}>
          {loading ? "Preparing..." : "Continue to card payment"}
        </button>
      </div>

      <h2 className="h2" style={{ marginTop: "24px", marginBottom: "10px" }}>
        Recent card top-ups
      </h2>
      <div className="txList" role="list">
        {orders.length ? (
          orders.map((order) => (
            <div key={order.id} className="txRow txRowStacked" role="listitem">
              <div className="txMain">
                <div className="txTitle">
                  {order.amount} {order.currency}
                </div>
                <div className="txSub">
                  {order.status}
                  {order.card_type ? ` • ${order.card_type}` : ""}
                  {order.transaction_id ? ` • txn ${order.transaction_id}` : ""}
                </div>
                <div className="txSub">Order #{order.provider_order_id}</div>
                <div className="txSub">{order.created_at}</div>
              </div>

              <div className="cardTopupActions">
                {order.status !== "completed" && order.redirect_url ? (
                  <button className="btn btnSoft" type="button" onClick={() => window.location.assign(order.redirect_url)}>
                    Open checkout
                  </button>
                ) : null}
                {order.status !== "completed" ? (
                  <button className="btn btnSoft" type="button" onClick={() => void refreshOrder(order.provider_order_id)}>
                    Refresh status
                  </button>
                ) : null}
              </div>
            </div>
          ))
        ) : (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">No card top-ups yet</div>
              <div className="txSub">Create your first secure checkout above.</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
