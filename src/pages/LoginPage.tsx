import { useEffect, useMemo, useState } from "react";
import LanguageToggle from "../components/LanguageToggle";
import { fleets, requestFleetCode, verifyFleetCode, type Fleet } from "../lib/api";
import { useI18n } from "../lib/i18n";

type Props = {
  onAuthenticated: () => Promise<void>;
};

export default function LoginPage({ onAuthenticated }: Props) {
  const { pick } = useI18n();
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
        setFleetLoadError(pick("Unable to load fleets right now.", "ფლიტების ჩატვირთვა ახლა ვერ მოხერხდა."));
      } finally {
        setFleetLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (fleetLoading || fleetList.length === 0) return;
    const fleetParam = new URLSearchParams(window.location.search).get("fleet")?.trim();
    if (!fleetParam) return;
    const matchedFleet = fleetList.find((fleet) => fleet.name.toLowerCase() === fleetParam.toLowerCase());
    if (!matchedFleet) {
      setFleetQuery(fleetParam);
      return;
    }
    setFleetQuery(matchedFleet.name);
    setSelectedFleetName(matchedFleet.name);
    setChallengeId(null);
    setCode("");
    setError("");
  }, [fleetList, fleetLoading]);

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
        setError(pick("Wrong number for this fleet.", "ამ ფლიტისთვის არასწორი ნომერია."));
      } else if (message.includes("Fleet not found")) {
        setError(pick("Fleet not found.", "ფლიტი ვერ მოიძებნა."));
      } else {
        setError(pick("Could not send code.", "კოდის გაგზავნა ვერ მოხერხდა."));
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
      setError(pick("Invalid or expired code.", "კოდი არასწორია ან ვადა გაუვიდა."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="loginPage">
      <section className="card loginCard">
        <div className="loginCardTop">
          <LanguageToggle />
        </div>
        <h1 className="loginTitle">{pick("Login To Fleet", "ფლიტში შესვლა")}</h1>

        <div className="transferForm">
          <label className="transferField">
            <span className="transferLabel">{pick("Search fleet", "ფლიტის ძიება")}</span>
            <input
              className="transferInput"
              type="text"
              placeholder={pick("Type fleet name", "ჩაწერეთ ფლიტის სახელი")}
              value={fleetQuery}
              onChange={(event) => setFleetQuery(event.target.value)}
            />
          </label>

          <div className="fleetResults" role="listbox" aria-label={pick("Fleet options", "ფლიტის ვარიანტები")}>
            {fleetLoading ? (
              <p className="statusHint">{pick("Loading fleets...", "ფლიტები იტვირთება...")}</p>
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
              <p className="statusHint">{pick("No fleets found.", "ფლიტები ვერ მოიძებნა.")}</p>
            ) : (
              <p className="statusHint">{pick("Start typing to search fleets.", "ძებნისთვის დაიწყეთ აკრეფა.")}</p>
            )}
          </div>

          {selectedFleetName ? (
            <>
              <p className="statusHint">{pick("Selected fleet", "არჩეული ფლიტი")}: {selectedFleetName}</p>
              <label className="transferField">
                <span className="transferLabel">{pick("Phone number", "ტელეფონის ნომერი")}</span>
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
              {loading ? pick("Sending...", "იგზავნება...") : pick("Receive code", "კოდის მიღება")}
            </button>
          ) : null}

          {challengeId ? (
            <>
              <label className="transferField">
                <span className="transferLabel">{pick("Code", "კოდი")}</span>
                <input
                  className="transferInput transferInputAccent"
                  type="text"
                  placeholder={pick("Enter 6-digit code", "შეიყვანეთ 6-ნიშნა კოდი")}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
              <button className="transferSubmit" type="button" onClick={() => void handleVerifyCode()}>
                {loading ? pick("Verifying...", "მოწმდება...") : pick("Login to fleet", "ფლიტში შესვლა")}
              </button>
            </>
          ) : null}
          {error ? <p className="statusError">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
