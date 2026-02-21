import { useState, type ReactNode } from "react";

export default function DashboardPage() {
  const [isBonusesOpen, setBonusesOpen] = useState(false);
  const [isTransferOpen, setTransferOpen] = useState(false);
  const [isWithdrawOpen, setWithdrawOpen] = useState(false);
  const [isRentOpen, setRentOpen] = useState(false);
  const balanceGel = 0;
  const transactions = [
    { id: "t1", title: "Transfer to bank", subtitle: "Pending", amountGel: -120.5 },
    { id: "t2", title: "Top up balance", subtitle: "Completed", amountGel: 250 },
    { id: "t3", title: "Transfer to someone", subtitle: "Completed", amountGel: -35 },
    { id: "t4", title: "Yandex payout", subtitle: "Completed", amountGel: 410.75 }
  ];

  return (
    <div className="dashboard">
      <div className="dashboardQuickRow">
        <IconButton label="Referrals" variant="ghost" icon={<IconReferral />} />
        <IconButton
          label="Bonuses"
          variant="ghost"
          icon={<IconGift />}
          onClick={() => setBonusesOpen(true)}
        />
        <IconButton label="Renting" variant="ghost" icon={<IconCar />} onClick={() => setRentOpen(true)} />
      </div>

      <section className="card balanceCard">
        <div className="balanceHeader">
          <div>
            <div className="muted">Your balance</div>
            <div className="balanceValue">{balanceGel.toFixed(2)} GEL</div>
          </div>
        </div>
      </section>

      <section className="card cardTransparent">
        <div className="actionRow" aria-label="Actions">
          <IconButton
            label="Transfer money"
            variant="soft"
            icon={<IconSend />}
            onClick={() => setWithdrawOpen(true)}
          />
          <IconButton
            label="Transfer to someone"
            variant="soft"
            icon={<IconUsers />}
            onClick={() => setTransferOpen(true)}
          />
          <IconButton label="Fill up balance" variant="soft" icon={<IconPlus />} />
          <IconButton label="Video tariffs" variant="soft" icon={<IconPlay />} />
        </div>
      </section>

      <section className="card">
        <div className="cardTitleRow">
          <h2 className="h2">Transaction history</h2>
          <button className="btn btnGhost" type="button">
            View all
          </button>
        </div>

        <div className="txList" role="list">
          {transactions.map((tx) => (
            <div key={tx.id} className="txRow" role="listitem">
              <div className="txMain">
                <div className="txTitle">{tx.title}</div>
                <div className="txSub">{tx.subtitle}</div>
              </div>
              <div className={`txAmount ${tx.amountGel < 0 ? "neg" : "pos"}`}>
                {tx.amountGel < 0 ? "-" : "+"}
                {Math.abs(tx.amountGel).toFixed(2)} GEL
              </div>
            </div>
          ))}
        </div>
      </section>

      {isBonusesOpen ? <BonusesModal onClose={() => setBonusesOpen(false)} /> : null}
      {isTransferOpen ? <TransferModal onClose={() => setTransferOpen(false)} /> : null}
      {isWithdrawOpen ? <WithdrawModal onClose={() => setWithdrawOpen(false)} /> : null}
      {isRentOpen ? <RentModal onClose={() => setRentOpen(false)} /> : null}
    </div>
  );
}

function IconButton({
  label,
  icon,
  variant = "soft",
  onClick
}: {
  label: string;
  icon: ReactNode;
  variant?: "ghost" | "soft";
  onClick?: () => void;
}) {
  const className = variant === "ghost" ? "iconBtn btnGhost" : "iconBtn btnSoft";
  return (
    <button className={className} type="button" aria-label={label} onClick={onClick}>
      <span className="iconBtnIcon" aria-hidden="true">
        {icon}
      </span>
      <span className="iconBtnLabel">{label}</span>
    </button>
  );
}

function BonusesModal({ onClose }: { onClose: () => void }) {
  const items = [
    { title: "Top Driver", icon: <IconMedal />, unread: true },
    { title: "Formula 1 Pro", icon: <IconFlag /> },
    { title: "Fuel", icon: <IconFuel /> },
    { title: "Referrals", icon: <IconReferralGroup /> },
    { title: "Cashback", icon: <IconMoneyBag /> },
    { title: "Star bonus", icon: <IconSpark />, muted: true }
  ];

  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="bonusModal"
        role="dialog"
        aria-modal="true"
        aria-label="Your bonuses"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close bonuses" onClick={onClose}>
          <IconClose />
        </button>

        <div className="bonusHeader">
          <span className="bonusTrophy" aria-hidden="true">
            <IconTrophy />
          </span>
          <h2 className="bonusTitle">Your bonuses</h2>
          <p className="bonusAmount">Total bonus given to drivers: 96,700.78 GEL</p>
          <p className="bonusAmount bonusAmountSecondary">You received: 0.00 GEL</p>
        </div>

        <div className="bonusGrid" role="list">
          {items.map((item) => (
            <button
              key={item.title}
              className={`bonusTile ${item.muted ? "bonusTileMuted" : ""}`}
              type="button"
              role="listitem"
            >
              {item.unread ? <span className="bonusBadge">1</span> : null}
              <span className="bonusTileIcon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="bonusTileLabel">{item.title}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function TransferModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="transferModal"
        role="dialog"
        aria-modal="true"
        aria-label="Transfer to someone"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close transfer" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="transferTitle">Transfer</h2>

        <form className="transferForm">
          <label className="transferField">
            <span className="transferLabel">Choose bank</span>
            <span className="transferSelectWrap">
              <select className="transferInput transferInputAccent" defaultValue="">
                <option value="" disabled>
                  Select bank
                </option>
                <option value="bog">Bank of Georgia</option>
                <option value="tbc">TBC Bank</option>
                <option value="liberty">Liberty Bank</option>
              </select>
              <span className="transferChevron" aria-hidden="true">
                <IconChevronDown />
              </span>
            </span>
          </label>

          <label className="transferField">
            <span className="transferLabel">Account number</span>
            <input className="transferInput" type="text" inputMode="numeric" placeholder="GE00 TB00 0000" />
          </label>

          <label className="transferField">
            <span className="transferLabel">Beneficiary name</span>
            <input className="transferInput" type="text" placeholder="Full name" />
          </label>

          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input className="transferInput" type="text" defaultValue="0.1489" />
          </label>

          <label className="transferField">
            <span className="transferLabel">Nomination</span>
            <input className="transferInput" type="text" defaultValue="Private transfer" />
          </label>

          <button className="transferSubmit" type="button">
            Transfer
          </button>
        </form>
      </section>
    </div>
  );
}

function WithdrawModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="transferModal"
        role="dialog"
        aria-modal="true"
        aria-label="Withdraw"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close withdraw" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="transferTitle">Withdraw</h2>

        <form className="transferForm">
          <label className="transferField">
            <span className="transferLabel">Choose bank</span>
            <span className="transferSelectWrap">
              <select className="transferInput" defaultValue="">
                <option value="" disabled>
                  Select bank
                </option>
                <option value="bog">Bank of Georgia</option>
                <option value="tbc">TBC Bank</option>
                <option value="liberty">Liberty Bank</option>
              </select>
              <span className="transferChevron" aria-hidden="true">
                <IconChevronDown />
              </span>
            </span>
          </label>

          <label className="transferField">
            <span className="transferLabel">Account number</span>
            <input className="transferInput" type="text" inputMode="numeric" placeholder="GE00 TB00 0000" />
          </label>

          <label className="transferField">
            <span className="transferLabel">Beneficiary name</span>
            <input className="transferInput" type="text" defaultValue="levani bagashvili" />
          </label>

          <label className="transferField">
            <span className="transferLabel">Amount</span>
            <input className="transferInput" type="text" defaultValue="0.1489" />
          </label>

          <button className="transferSubmit" type="button">
            Withdrawal
          </button>
        </form>
      </section>
    </div>
  );
}

function RentModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="bonusOverlay" role="presentation" onClick={onClose}>
      <section
        className="rentModal"
        role="dialog"
        aria-modal="true"
        aria-label="Rent a car"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="bonusClose" type="button" aria-label="Close rent modal" onClick={onClose}>
          <IconClose />
        </button>

        <h2 className="rentTitle">Rent a car</h2>
        <p className="rentCopy">
          Taxio is a platform where you can quickly and easily rent the car you want to work as a
          taxi.
        </p>

        <a
          className="transferSubmit rentSubmit"
          href="https://taxio.ge/"
          target="_blank"
          rel="noreferrer"
        >
          View cars
        </a>
      </section>
    </div>
  );
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4 12L20 4l-4 16-4.5-6L4 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M20 4 11.5 14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconUsers() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M16 11a3 3 0 1 0-2.999-3A3 3 0 0 0 16 11Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M8.5 12a2.5 2.5 0 1 0-2.5-2.5A2.5 2.5 0 0 0 8.5 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M12.5 20c.3-2.7 2.6-5 5.5-5s5.2 2.3 5.5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M1 20c.2-2.2 2.1-4 4.5-4 1.2 0 2.3.4 3.1 1.1"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconPlay() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4.5 8.5A2.5 2.5 0 0 1 7 6h7a2.5 2.5 0 0 1 2.5 2.5V9l2.9-1.9c.8-.5 1.8.1 1.8 1v7.8c0 .9-1 1.5-1.8 1L16.5 15v.5A2.5 2.5 0 0 1 14 18H7a2.5 2.5 0 0 1-2.5-2.5v-7Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="10.5" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M9 6V4.8a.8.8 0 0 1 .8-.8h1.4a.8.8 0 0 1 .8.8V6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconGift() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M20 12v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M4 12h16V8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v4Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M12 6v16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M12 6c-1.6 0-3-1.2-3-2.5S10.4 1 12 3c1.6-2 3-1.5 3 .5S13.6 6 12 6Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconCar() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M4.8 12.8 8 8.5c.4-.6 1.1-.9 1.8-.9h4.4c.7 0 1.4.3 1.8.9l3.2 4.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M5.2 12.7h13.6a1.8 1.8 0 0 1 1.8 1.8v2.1H3.4v-2.1a1.8 1.8 0 0 1 1.8-1.8Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M6.6 16.6v1.8M17.4 16.6v1.8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="8.2" cy="14.8" r="1.1" fill="currentColor" />
      <circle cx="15.8" cy="14.8" r="1.1" fill="currentColor" />
      <path d="M9.8 10.6h4.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function IconReferral() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path
        d="M10.5 13a3.5 3.5 0 1 1 0-5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M13.5 11a3.5 3.5 0 1 1 0 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M9.8 12h4.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconClose() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconTrophy() {
  return (
    <svg viewBox="0 0 24 24" width="30" height="30" fill="none" aria-hidden="true">
      <path
        d="M7 4h10v2a5 5 0 0 1-10 0V4ZM12 11v3M9 20h6M10 14h4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M17 6h2a2 2 0 0 1-2 2M7 6H5a2 2 0 0 0 2 2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconMedal() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M10 4h4l-1.3 4h-1.4L10 4Z" fill="currentColor" />
      <path d="m10 16-1 4 3-1.5L15 20l-1-4" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function IconFlag() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path d="M7 4v16M7 6h10l-2.2 2L17 10H7" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function IconFuel() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="M7 6h7v12H7V6Zm7 2h2l1.5 2.2V16a1.5 1.5 0 1 0 3 0v-5l-2-2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconReferralGroup() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <circle cx="12" cy="9" r="2.8" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.2 18c.8-2 2.8-3.2 5-3.2s4.2 1.2 5 3.2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="6.5" cy="10.4" r="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17.5" cy="10.4" r="2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function IconMoneyBag() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="M12 6c4 0 6.5 3 6.5 6.3A6.5 6.5 0 0 1 12 19a6.5 6.5 0 0 1-6.5-6.7C5.5 9 8 6 12 6Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path d="M10 4h4l-1.2 2.2h-1.6L10 4Z" fill="currentColor" />
      <path d="M12 9v6M10 11.2c0-1 4-1 4 0s-4 1-4 2 4 1 4 0" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function IconSpark() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" aria-hidden="true">
      <path
        d="m12 3 2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2L12 3Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconChevronDown() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true">
      <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}
