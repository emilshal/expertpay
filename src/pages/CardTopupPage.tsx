import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  bogCardOrders,
  createBogCardOrder,
  syncBogCardOrder,
  type BogCardOrder
} from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function CardTopupPage() {
  const { pick } = useI18n();
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
      setError(pick("Unable to load card top-up orders right now.", "ბარათით შევსების შეკვეთები ახლა ვერ ჩაიტვირთა."));
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
      setMessage(pick("Secure Bank of Georgia checkout created. Redirecting now...", "Bank of Georgia-ს დაცული ჩექაუთი შეიქმნა. ახლა გადამისამართდება..."));
      await loadOrders();
      if (order.redirect_url) {
        window.location.assign(order.redirect_url);
        return;
      }
      setError(pick("BoG returned an order but no redirect URL.", "BoG-მა შეკვეთა დააბრუნა, მაგრამ გადამისამართების მისამართი არა."));
    } catch (checkoutError) {
      setError(checkoutError instanceof Error ? checkoutError.message : pick("Unable to start card payment.", "ბარათით გადახდის დაწყება ვერ მოხერხდა."));
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
      setMessage(pick(`Order ${order.provider_order_id} is now ${order.status}.`, `შეკვეთა ${order.provider_order_id} ახლა არის ${order.status}.`));
      await loadOrders();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : pick("Unable to refresh card order.", "ბარათის შეკვეთის განახლება ვერ მოხერხდა."));
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <div className="cardTitleRow">
        <h1>{pick("Card top-up", "ბარათით შევსება")}</h1>
        <div className="toolbarRow">
          <button className="btn btnGhost" type="button" onClick={() => navigate("/deposits")}>
            {pick("Bank transfer", "საბანკო გადარიცხვა")}
          </button>
          <button className="btn btnGhost" type="button" onClick={() => void loadOrders()}>
            {pick("Refresh list", "სიის განახლება")}
          </button>
        </div>
      </div>

      <p className="muted">
        {pick(
          "Fund your fleet reserve with Bank of Georgia's hosted checkout. After payment, return here and refresh the order status if it has not updated yet.",
          "შეავსეთ ფლიტის რეზერვი Bank of Georgia-ს ჩაშენებული ჩექაუთით. გადახდის შემდეგ დაბრუნდით აქ და, საჭიროების შემთხვევაში, განაახლეთ შეკვეთის სტატუსი."
        )}
      </p>

      {error ? <p className="statusError" style={{ marginTop: "12px" }}>{error}</p> : null}
      {message ? <p className="statusHint" style={{ marginTop: "12px" }}>{message}</p> : null}

      <div className="cardTopupForm">
        <label className="cardTopupField">
          <span className="txSub">{pick("Amount (GEL)", "თანხა (GEL)")}</span>
          <input
            className="transferInput"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="25.00"
          />
        </label>
        <button className="transferSubmit" type="button" onClick={() => void startCheckout()} disabled={loading}>
          {loading ? pick("Preparing...", "მზადდება...") : pick("Continue to card payment", "გადასვლა ბარათით გადახდაზე")}
        </button>
      </div>

      <h2 className="h2" style={{ marginTop: "24px", marginBottom: "10px" }}>
        {pick("Recent card top-ups", "ბოლო ბარათით შევსებები")}
      </h2>
      <div className="txList" role="list">
        {orders.length ? (
          orders.map((order) => (
            <div key={order.id} className="txRow txRowStacked" role="listitem">
              <div className="txMain">
                <div className="txTitle">
                  {order.amount} {order.currency}
                </div>
                {order.fleet_name ? <div className="txSub">{pick("Fleet", "ფლიტი")}: {order.fleet_name}</div> : null}
                <div className="txSub">
                  {order.status}
                  {order.card_type ? ` • ${order.card_type}` : ""}
                  {order.transaction_id ? ` • txn ${order.transaction_id}` : ""}
                </div>
                <div className="txSub">{pick("Order", "შეკვეთა")} #{order.provider_order_id}</div>
                <div className="txSub">{order.created_at}</div>
              </div>

              <div className="cardTopupActions">
                {order.status !== "completed" && order.redirect_url ? (
                  <button className="btn btnSoft" type="button" onClick={() => window.location.assign(order.redirect_url)}>
                    {pick("Open checkout", "ჩექაუთის გახსნა")}
                  </button>
                ) : null}
                {order.status !== "completed" ? (
                  <button className="btn btnSoft" type="button" onClick={() => void refreshOrder(order.provider_order_id)}>
                    {pick("Refresh status", "სტატუსის განახლება")}
                  </button>
                ) : null}
              </div>
            </div>
          ))
        ) : (
          <div className="txRow" role="listitem">
            <div className="txMain">
              <div className="txTitle">{pick("No card top-ups yet", "ბარათით შევსება ჯერ არ არის")}</div>
              <div className="txSub">{pick("Create your first secure checkout above.", "ზემოთ შექმენით თქვენი პირველი დაცული ჩექაუთი.")}</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
