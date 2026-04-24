import { useEffect, useMemo, useState } from "react";
import LanguageToggle from "../components/LanguageToggle";
import { fleets, registerDriver, registerFleet, requestFleetCode, verifyFleetCode, type Fleet } from "../lib/api";
import { useI18n } from "../lib/i18n";

type Props = {
  onAuthenticated: () => Promise<void>;
};

export default function LoginPage({ onAuthenticated }: Props) {
  const { pick } = useI18n();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [registrationType, setRegistrationType] = useState<"fleet" | "driver">("fleet");
  const [loginRole, setLoginRole] = useState<"driver" | "owner">("driver");
  const [fleetList, setFleetList] = useState<Fleet[]>([]);
  const [fleetQuery, setFleetQuery] = useState("");
  const [selectedFleetName, setSelectedFleetName] = useState("");
  const [phone, setPhone] = useState("");
  const [registrationFleetName, setRegistrationFleetName] = useState("");
  const [registrationFirstName, setRegistrationFirstName] = useState("");
  const [registrationLastName, setRegistrationLastName] = useState("");
  const [registrationEmail, setRegistrationEmail] = useState("");
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

  const canRegisterFleet = useMemo(
    () => Boolean(registrationFleetName.trim() && phone.trim()),
    [registrationFleetName, phone]
  );

  const canRegisterDriver = useMemo(
    () => Boolean(selectedFleetName.trim() && phone.trim()),
    [selectedFleetName, phone]
  );

  async function handleRegisterFleet() {
    if (!canRegisterFleet) return;
    setLoading(true);
    setError("");
    try {
      const fleet = await registerFleet({
        fleet_name: registrationFleetName.trim(),
        phone_number: phone.trim(),
        first_name: registrationFirstName.trim(),
        last_name: registrationLastName.trim(),
        email: registrationEmail.trim()
      });
      setFleetList((current) => [fleet, ...current.filter((item) => item.id !== fleet.id)]);
      setSelectedFleetName(fleet.name);
      setFleetQuery(fleet.name);
      setMode("login");
      const data = await requestFleetCode({ fleet_name: fleet.name, phone_number: phone.trim(), role: "owner" });
      setChallengeId(data.challenge_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (message.includes("Fleet already exists")) {
        setError(pick("Fleet already exists.", "ფლიტი უკვე არსებობს."));
      } else if (message.includes("phone number is already registered")) {
        setError(pick("This phone number is already registered.", "ეს ტელეფონის ნომერი უკვე რეგისტრირებულია."));
      } else {
        setError(pick("Could not register fleet.", "ფლიტის რეგისტრაცია ვერ მოხერხდა."));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRegisterDriver() {
    if (!canRegisterDriver) return;
    setLoading(true);
    setError("");
    try {
      await registerDriver({
        fleet_name: selectedFleetName.trim(),
        phone_number: phone.trim(),
        first_name: registrationFirstName.trim(),
        last_name: registrationLastName.trim(),
        email: registrationEmail.trim()
      });
      setMode("login");
      const data = await requestFleetCode({ fleet_name: selectedFleetName.trim(), phone_number: phone.trim(), role: "driver" });
      setChallengeId(data.challenge_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (message.includes("Fleet not found")) {
        setError(pick("Fleet not found.", "ფლიტი ვერ მოიძებნა."));
      } else if (message.includes("phone number is already registered")) {
        setError(pick("This phone number is already registered.", "ეს ტელეფონის ნომერი უკვე რეგისტრირებულია."));
      } else {
        setError(pick("Could not register driver.", "მძღოლის რეგისტრაცია ვერ მოხერხდა."));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRequestCode() {
    if (!canRequestCode) return;
    setLoading(true);
    setError("");
    try {
      const internalAdminLogin = selectedFleetName.trim().toLowerCase() === "new tech" && phone.trim() === "598950001";
      const data = await requestFleetCode({
        fleet_name: selectedFleetName.trim(),
        phone_number: phone.trim(),
        role: internalAdminLogin ? "admin" : loginRole,
        internal_admin_login: internalAdminLogin
      });
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
        <h1 className="loginTitle">
          {mode === "register"
            ? registrationType === "fleet"
              ? pick("Register Fleet", "ფლიტის რეგისტრაცია")
              : pick("Register Driver", "მძღოლის რეგისტრაცია")
            : pick("Login To Fleet", "ფლიტში შესვლა")}
        </h1>
        <div className="loginModeSwitch" role="tablist" aria-label={pick("Authentication mode", "ავტორიზაციის ტიპი")}>
          <button
            type="button"
            className={`loginModeButton ${mode === "register" ? "loginModeButtonActive" : ""}`}
            disabled={loading}
            onClick={() => {
              setMode("register");
              setChallengeId(null);
              setCode("");
              setError("");
            }}
          >
            {pick("Register", "რეგისტრაცია")}
          </button>
          <button
            type="button"
            className={`loginModeButton ${mode === "login" ? "loginModeButtonActive" : ""}`}
            disabled={loading}
            onClick={() => {
              setMode("login");
              setChallengeId(null);
              setCode("");
              setError("");
            }}
          >
            {pick("Login", "შესვლა")}
          </button>
        </div>

        <div className="transferForm">
          {mode === "register" ? (
            <>
              <div className="loginModeSwitch loginModeSwitchCompact" role="tablist" aria-label={pick("Registration type", "რეგისტრაციის ტიპი")}>
                <button
                  type="button"
                  className={`loginModeButton ${registrationType === "fleet" ? "loginModeButtonActive" : ""}`}
                  disabled={loading}
                  onClick={() => {
                    setRegistrationType("fleet");
                    setChallengeId(null);
                    setCode("");
                    setError("");
                  }}
                >
                  {pick("Fleet", "ფლიტი")}
                </button>
                <button
                  type="button"
                  className={`loginModeButton ${registrationType === "driver" ? "loginModeButtonActive" : ""}`}
                  disabled={loading}
                  onClick={() => {
                    setRegistrationType("driver");
                    setChallengeId(null);
                    setCode("");
                    setError("");
                  }}
                >
                  {pick("Driver", "მძღოლი")}
                </button>
              </div>

              {registrationType === "fleet" ? (
                <label className="transferField">
                  <span className="transferLabel">{pick("Fleet name", "ფლიტის სახელი")}</span>
                  <input
                    className="transferInput"
                    type="text"
                    placeholder={pick("Example Taxi Fleet", "მაგალითად ტაქსის ფლიტი")}
                    value={registrationFleetName}
                    onChange={(event) => setRegistrationFleetName(event.target.value)}
                  />
                </label>
              ) : (
                <>
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
                    <p className="statusHint">{pick("Selected fleet", "არჩეული ფლიტი")}: {selectedFleetName}</p>
                  ) : null}
                </>
              )}

              <label className="transferField">
                <span className="transferLabel">
                  {registrationType === "fleet" ? pick("Your name", "თქვენი სახელი") : pick("Driver name", "მძღოლის სახელი")}
                </span>
                <input
                  className="transferInput"
                  type="text"
                  placeholder={pick("First name", "სახელი")}
                  value={registrationFirstName}
                  onChange={(event) => setRegistrationFirstName(event.target.value)}
                />
              </label>
              <label className="transferField">
                <span className="transferLabel">{pick("Last name", "გვარი")}</span>
                <input
                  className="transferInput"
                  type="text"
                  placeholder={pick("Last name", "გვარი")}
                  value={registrationLastName}
                  onChange={(event) => setRegistrationLastName(event.target.value)}
                />
              </label>
              <label className="transferField">
                <span className="transferLabel">{pick("Email", "ელფოსტა")}</span>
                <input
                  className="transferInput"
                  type="email"
                  placeholder="name@example.com"
                  value={registrationEmail}
                  onChange={(event) => setRegistrationEmail(event.target.value)}
                />
              </label>
            </>
          ) : (
            <>
              <div className="loginModeSwitch loginModeSwitchCompact" role="tablist" aria-label={pick("Login role", "შესვლის როლი")}>
                <button
                  type="button"
                  className={`loginModeButton ${loginRole === "driver" ? "loginModeButtonActive" : ""}`}
                  disabled={loading}
                  onClick={() => {
                    setLoginRole("driver");
                    setChallengeId(null);
                    setCode("");
                    setError("");
                  }}
                >
                  {pick("Driver", "მძღოლი")}
                </button>
                <button
                  type="button"
                  className={`loginModeButton ${loginRole === "owner" ? "loginModeButtonActive" : ""}`}
                  disabled={loading}
                  onClick={() => {
                    setLoginRole("owner");
                    setChallengeId(null);
                    setCode("");
                    setError("");
                  }}
                >
                  {pick("Owner", "მფლობელი")}
                </button>
              </div>

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
                <p className="statusHint">{pick("Selected fleet", "არჩეული ფლიტი")}: {selectedFleetName}</p>
              ) : null}
            </>
          )}

          {(mode === "register" || selectedFleetName) && !challengeId ? (
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
          ) : null}

          {!challengeId && mode === "register" ? (
            <button
              className="transferSubmit"
              type="button"
              onClick={() => registrationType === "fleet" ? void handleRegisterFleet() : void handleRegisterDriver()}
            >
              {loading
                ? pick("Registering...", "რეგისტრირდება...")
                : registrationType === "fleet"
                  ? pick("Register fleet and receive code", "ფლიტის რეგისტრაცია და კოდის მიღება")
                  : pick("Register driver and receive code", "მძღოლის რეგისტრაცია და კოდის მიღება")}
            </button>
          ) : null}

          {!challengeId && mode === "login" && selectedFleetName ? (
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
