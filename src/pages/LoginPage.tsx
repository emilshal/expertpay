import { useEffect, useMemo, useState } from "react";
import { fleets, requestFleetCode, verifyFleetCode, type Fleet } from "../lib/api";

type Props = {
  onAuthenticated: () => Promise<void>;
};

export default function LoginPage({ onAuthenticated }: Props) {
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [fleetName, setFleetName] = useState("");
  const [phone, setPhone] = useState("");
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [debugCode, setDebugCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const data = await fleets();
        setFleetList(data);
      } catch {
        setError("Unable to load fleets.");
      }
    })();
  }, []);

  const canRequestCode = useMemo(() => Boolean(fleetName.trim() && phone.trim()), [fleetName, phone]);

  async function handleRequestCode() {
    if (!canRequestCode) return;
    setLoading(true);
    setError("");
    try {
      const data = await requestFleetCode({ fleet_name: fleetName.trim(), phone_number: phone.trim() });
      setChallengeId(data.challenge_id);
      setDebugCode(data.code ?? "");
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (message.includes("Wrong number")) {
        setError("Wrong number for this fleet.");
      } else if (message.includes("Fleet not found")) {
        setError("Fleet not found.");
      } else {
        setError("Could not send code.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyCode() {
    if (!challengeId || !code.trim()) return;
    setLoading(true);
    setError("");
    try {
      await verifyFleetCode({ challenge_id: challengeId, code: code.trim() });
      await onAuthenticated();
    } catch {
      setError("Invalid or expired code.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="loginPage">
      <section className="card loginCard">
        <h1 className="loginTitle">Login To Fleet</h1>
        <p className="loginSubtitle">Choose your fleet, enter phone number, then verify with code.</p>

        <div className="transferForm">
          <label className="transferField">
            <span className="transferLabel">Choose your fleet</span>
            <span className="transferSelectWrap">
              <select
                className="transferInput"
                value={fleetName}
                onChange={(event) => setFleetName(event.target.value)}
              >
                <option value="">Select fleet</option>
                {fleetList.map((fleet) => (
                  <option key={fleet.id} value={fleet.name}>
                    {fleet.name}
                  </option>
                ))}
              </select>
              <span className="transferChevron" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
                  <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
                </svg>
              </span>
            </span>
          </label>

          <label className="transferField">
            <span className="transferLabel">Phone number</span>
            <input
              className="transferInput"
              type="tel"
              placeholder="+995 5XX XX XX XX"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </label>

          {!challengeId ? (
            <button className="transferSubmit" type="button" onClick={() => void handleRequestCode()}>
              {loading ? "Sending..." : "Receive code"}
            </button>
          ) : (
            <>
              <label className="transferField">
                <span className="transferLabel">Code</span>
                <input
                  className="transferInput transferInputAccent"
                  type="text"
                  placeholder="Enter 6-digit code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
              <button className="transferSubmit" type="button" onClick={() => void handleVerifyCode()}>
                {loading ? "Verifying..." : "Login to fleet"}
              </button>
            </>
          )}

          {debugCode ? <p className="statusHint">Test code: {debugCode}</p> : null}
          {error ? <p className="statusError">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
