import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";

type Platform = "iphone" | "android";

type Props = {
  variant?: "button" | "icon";
};

function DownloadGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v11" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 20h14" />
    </svg>
  );
}

export default function InstallAppGuide({ variant = "button" }: Props) {
  const { pick } = useI18n();
  const [isOpen, setOpen] = useState(false);
  const [platform, setPlatform] = useState<Platform>("iphone");

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  const steps = platform === "iphone"
    ? [
        pick("Open ExpertPay in Safari.", "გახსენით ExpertPay Safari-ში."),
        pick("Tap the Share button at the bottom of the browser.", "დააჭირეთ Share ღილაკს ბრაუზერის ქვედა ნაწილში."),
        pick("Choose Add to Home Screen.", "აირჩიეთ Add to Home Screen."),
        pick("Tap Add, then open ExpertPay from your home screen.", "დააჭირეთ Add-ს და გახსენით ExpertPay მთავარი ეკრანიდან.")
      ]
    : [
        pick("Open ExpertPay in Chrome.", "გახსენით ExpertPay Chrome-ში."),
        pick("Tap the three-dot menu in the top right.", "დააჭირეთ ზედა მარჯვენა სამწერტილიან მენიუს."),
        pick("Choose Add to Home screen or Install app.", "აირჩიეთ Add to Home screen ან Install app."),
        pick("Confirm Install, then open ExpertPay from your home screen.", "დაადასტურეთ Install და გახსენით ExpertPay მთავარი ეკრანიდან.")
      ];

  return (
    <>
      <button
        className={variant === "icon" ? "installGuideIconButton" : "installGuideButton"}
        type="button"
        aria-label={pick("Download app", "აპის ჩამოტვირთვა")}
        title={pick("Download app", "აპის ჩამოტვირთვა")}
        onClick={() => setOpen(true)}
      >
        {variant === "icon" ? <DownloadGlyph /> : pick("Download app", "აპის ჩამოტვირთვა")}
      </button>

      {isOpen ? (
        <div className="installGuideOverlay" role="presentation" onMouseDown={() => setOpen(false)}>
          <section
            className="installGuidePanel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="install-guide-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="installGuideHeader">
              <div>
                <div className="installGuideEyebrow">{pick("Home screen app", "მთავარი ეკრანის აპი")}</div>
                <h2 id="install-guide-title" className="installGuideTitle">
                  {pick("Install ExpertPay", "ExpertPay-ის დაყენება")}
                </h2>
              </div>
              <button className="installGuideClose" type="button" aria-label={pick("Close", "დახურვა")} onClick={() => setOpen(false)}>
                X
              </button>
            </div>

            <div className="installGuideTabs" role="tablist" aria-label={pick("Choose device", "აირჩიეთ მოწყობილობა")}>
              <button
                className={`installGuideTab ${platform === "iphone" ? "installGuideTabActive" : ""}`}
                type="button"
                onClick={() => setPlatform("iphone")}
              >
                iPhone
              </button>
              <button
                className={`installGuideTab ${platform === "android" ? "installGuideTabActive" : ""}`}
                type="button"
                onClick={() => setPlatform("android")}
              >
                Android
              </button>
            </div>

            <ol className="installGuideSteps">
              {steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </section>
        </div>
      ) : null}
    </>
  );
}
