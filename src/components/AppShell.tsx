import { PropsWithChildren } from "react";

export default function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brandMark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
              <path
                d="M12 6.2v11"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
              <path
                d="M15.8 7.6c0-1.7-1.7-3.1-3.8-3.1S8.2 5.9 8.2 7.6 9.8 10 12 10s3.8 1.2 3.8 3-1.7 3.1-3.8 3.1S8.2 14.7 8.2 13"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="brandText">ExpertPay</div>
        </div>
      </header>

      <main className="main">{children}</main>
    </div>
  );
}
