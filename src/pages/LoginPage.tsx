import { useEffect, useMemo, useState } from "react";
import { fleets, requestFleetCode, verifyFleetCode, type Fleet } from "../lib/api";

type Props = {
  onAuthenticated: () => Promise<void>;
};

export default function LoginPage({ onAuthenticated }: Props) {
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [fleetQuery, setFleetQuery] = useState("");
  const [selectedFleetName, setSelectedFleetName] = useState("");
  const [phone, setPhone] = useState("");
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [fleetLoading, setFleetLoading] = useState(true);
  const [fleetLoadError, setFleetLoadError] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        setFleetLoading(true);
        setFleetLoadError("");
        const data = await fleets();
        setFleetList(data);
      } catch {
        setFleetLoadError("Unable to load fleets right now.");
      } finally {
        setFleetLoading(false);
      }
    })();
  }, []);

  const filteredFleets = useMemo(() => {
    const query = fleetQuery.trim().toLowerCase();
    if (!query) return fleetList;
    return fleetList.filter((fleet) => fleet.name.toLowerCase().includes(query));
  }, [fleetList, fleetQuery]);

  const canRequestCode = useMemo(
    () => Boolean(selectedFleetName.trim() && phone.trim()),
    [selectedFleetName, phone]
  );

  async function handleRequestCode() {
    if (!canRequestCode) return;
    setLoading(true);
    setError("");
    try {
      const data = await requestFleetCode({ fleet_name: selectedFleetName.trim(), phone_number: phone.trim() });
      setChallengeId(data.challenge_id);
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

        <div className="transferForm">
          <label className="transferField">
            <span className="transferLabel">Search fleet</span>
            <input
              className="transferInput"
              type="text"
              placeholder="Type fleet name"
              value={fleetQuery}
              onChange={(event) => setFleetQuery(event.target.value)}
            />
          </label>

          <div className="fleetResults" role="listbox" aria-label="Fleet options">
            {fleetLoading ? (
              <p className="statusHint">Loading fleets...</p>
            ) : fleetLoadError ? (
              <p className="statusError">{fleetLoadError}</p>
            ) : filteredFleets.length ? (
              filteredFleets.slice(0, 8).map((fleet) => (
                <button
                  key={fleet.id}
                  type="button"
                  className={`fleetOption ${selectedFleetName === fleet.name ? "fleetOptionActive" : ""}`}
                  onClick={() => {
                    setSelectedFleetName(fleet.name);
                    setChallengeId(null);
                    setCode("");
                    setError("");
                  }}
                >
                  {fleet.name}
                </button>
              ))
            ) : fleetQuery.trim() ? (
              <p className="statusHint">No fleets found.</p>
            ) : (
              <p className="statusHint">Start typing to search fleets.</p>
            )}
          </div>

          {selectedFleetName ? (
            <>
              <p className="statusHint">Selected fleet: {selectedFleetName}</p>
              <label className="transferField">
                <span className="transferLabel">Phone number</span>
                <div className="phoneInputWrap">
                  <span className="phonePrefix">+995</span>
                  <input
                    className="transferInput phoneInput"
                    type="tel"
                    inputMode="numeric"
                    placeholder="598950001"
                    value={phone}
                    onChange={(event) => {
                      let value = event.target.value.replace(/\D/g, "");
                      if (value.startsWith("995")) value = value.slice(3);
                      setPhone(value.slice(0, 9));
                    }}
                  />
                </div>
              </label>
            </>
          ) : null}

          {!challengeId && selectedFleetName ? (
            <button className="transferSubmit" type="button" onClick={() => void handleRequestCode()}>
              {loading ? "Sending..." : "Receive code"}
            </button>
          ) : null}

          {challengeId ? (
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
          ) : null}
          {error ? <p className="statusError">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
