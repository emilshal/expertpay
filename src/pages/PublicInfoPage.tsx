import { useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useI18n } from "../lib/i18n";

const COMPANY_NAME = "LTD EKSPERT PAY";
const COMPANY_ID = "406552145";
const CONTACT_PHONE = "598950001";
const CONTACT_EMAIL = "emil@hfield.net";
const CONTACT_ADDRESS = "Kakha Shevardenidze 3, Tbilisi, Georgia";

type SectionBlock =
  | { type: "paragraph"; en: string; ka: string }
  | { type: "list"; titleEn?: string; titleKa?: string; items: Array<{ en: string; ka: string }> }
  | { type: "facts"; items: Array<{ labelEn: string; labelKa: string; value: string }> };

type PageContent = {
  titleEn: string;
  titleKa: string;
  introEn: string;
  introKa: string;
  blocks: SectionBlock[];
};

const CONTENT: Record<string, PageContent> = {
  "/service": {
    titleEn: "Service Description",
    titleKa: "სერვისის აღწერა",
    introEn:
      "ExpertPay is a fleet payout platform for taxi businesses. Fleets fund their reserve, drivers request withdrawals inside the app, and operators or owners monitor payout status and reconciliation.",
    introKa:
      "ExpertPay არის ფლიტებისთვის განკუთვნილი გატანის პლატფორმა ტაქსის ბიზნესისთვის. ფლიტები ავსებენ რეზერვს, მძღოლები აპიდან ითხოვენ გატანას, ხოლო ოპერატორები და მფლობელები აკონტროლებენ სტატუსს და შერიგებას.",
    blocks: [
      {
        type: "list",
        titleEn: "Main services",
        titleKa: "ძირითადი სერვისები",
        items: [
          {
            en: "Fleet funding into a dedicated reserve balance.",
            ka: "ფლიტის შევსება სპეციალურ რეზერვის ბალანსზე."
          },
          {
            en: "Driver withdrawal requests inside the app.",
            ka: "მძღოლის მიერ გატანის მოთხოვნა აპლიკაციიდან."
          },
          {
            en: "Payout monitoring and operational review for fleets.",
            ka: "გატანების მონიტორინგი და ოპერაციული კონტროლი ფლიტებისთვის."
          }
        ]
      },
      {
        type: "list",
        titleEn: "Pricing and currency",
        titleKa: "ფასი და ვალუტა",
        items: [
          {
            en: "All amounts are displayed in GEL unless otherwise stated.",
            ka: "ყველა თანხა ნაჩვენებია ლარში, თუ სხვაგვარად არ არის მითითებული."
          },
          {
            en: "The driver withdrawal fee currently shown in the app is GEL 0.50 per withdrawal.",
            ka: "მძღოლის გატანის საკომისიო, რომელიც ამჟამად ნაჩვენებია აპში, არის 0.50 ლარი თითო გატანაზე."
          },
          {
            en: "Any funding amount, fee, and currency are shown to the user before payment is confirmed.",
            ka: "ნებისმიერი შევსების თანხა, საკომისიო და ვალუტა მომხმარებელს ეჩვენება გადახდის დადასტურებამდე."
          }
        ]
      }
    ]
  },
  "/about": {
    titleEn: "About Us",
    titleKa: "ჩვენ შესახებ",
    introEn:
      "ExpertPay provides payment operations software for taxi fleets, including funding workflows, driver withdrawals, payout monitoring, and treasury visibility.",
    introKa:
      "ExpertPay ტაქსის ფლიტებისთვის უზრუნველყოფს გადახდის ოპერაციების პროგრამულ უზრუნველყოფას, მათ შორის შევსების პროცესებს, მძღოლის გატანებს, სტატუსების მონიტორინგს და ხაზინის ხილვადობას.",
    blocks: [
      {
        type: "facts",
        items: [
          { labelEn: "Company name", labelKa: "კომპანიის სახელი", value: COMPANY_NAME },
          { labelEn: "Identification code", labelKa: "საიდენტიფიკაციო კოდი", value: COMPANY_ID }
        ]
      },
      {
        type: "paragraph",
        en: "The platform is designed for fleet owners, operators, and drivers who need transparent reserve management and controlled payouts.",
        ka: "პლატფორმა განკუთვნილია ფლიტის მფლობელებისთვის, ოპერატორებისთვის და მძღოლებისთვის, რომლებსაც სჭირდებათ გამჭვირვალე რეზერვის მართვა და კონტროლირებადი გატანები."
      }
    ]
  },
  "/contact": {
    titleEn: "Contact Information",
    titleKa: "საკონტაქტო ინფორმაცია",
    introEn:
      "Customers and partners can contact the merchant through the channels below.",
    introKa:
      "მომხმარებლებს და პარტნიორებს შეუძლიათ მერჩანტს დაუკავშირდნენ ქვემოთ მოცემული არხებით.",
    blocks: [
      {
        type: "facts",
        items: [
          { labelEn: "Phone", labelKa: "ტელეფონი", value: CONTACT_PHONE },
          { labelEn: "Email", labelKa: "ელფოსტა", value: CONTACT_EMAIL },
          { labelEn: "Address", labelKa: "მისამართი", value: CONTACT_ADDRESS }
        ]
      }
    ]
  },
  "/refund-policy": {
    titleEn: "Delivery, Cancellation, and Refund Policy",
    titleKa: "მიწოდების, გაუქმების და თანხის დაბრუნების პოლიტიკა",
    introEn:
      "ExpertPay provides digital payment and payout services. There is no physical delivery. Payment and payout processing depends on the selected payment rail and verification status.",
    introKa:
      "ExpertPay გთავაზობთ ციფრულ გადახდისა და გატანის სერვისებს. ფიზიკური მიწოდება არ ხდება. გადახდისა და გატანის დამუშავება დამოკიდებულია არჩეულ გადახდის არხზე და ვერიფიკაციის სტატუსზე.",
    blocks: [
      {
        type: "list",
        titleEn: "Cancellation and refund rules",
        titleKa: "გაუქმებისა და თანხის დაბრუნების წესები",
        items: [
          {
            en: "If a payment fails or is not completed, the user is not charged successfully and no payout is created.",
            ka: "თუ გადახდა ვერ შესრულდა ან არ დასრულდა, მომხმარებელი წარმატებით არ ირიცხება და გატანა არ იქმნება."
          },
          {
            en: "If a duplicate or incorrect payment is reported, the merchant reviews the case manually before any refund decision.",
            ka: "დუბლირებული ან არასწორი გადახდის შესახებ შეტყობინების შემთხვევაში, თანხის დაბრუნებამდე საქმე ხელით განიხილება."
          },
          {
            en: "Processed fleet funding and completed driver payouts may not be reversible after settlement and are reviewed individually.",
            ka: "დამუშავებული ფლიტის შევსება და დასრულებული მძღოლის გატანები ანგარიშსწორების შემდეგ შეიძლება აღარ იყოს გაუქმებადი და განიხილება ინდივიდუალურად."
          }
        ]
      }
    ]
  },
  "/privacy": {
    titleEn: "Privacy Policy",
    titleKa: "კონფიდენციალურობის პოლიტიკა",
    introEn:
      "ExpertPay processes personal and transactional data only to provide fleet funding, withdrawals, user authentication, operational support, and legal compliance.",
    introKa:
      "ExpertPay ამუშავებს პერსონალურ და ტრანზაქციულ მონაცემებს მხოლოდ ფლიტის შევსების, გატანის, მომხმარებლის ავთენტიფიკაციის, ოპერაციული მხარდაჭერისა და სამართლებრივი შესაბამისობის უზრუნველსაყოფად.",
    blocks: [
      {
        type: "list",
        titleEn: "Data categories",
        titleKa: "მონაცემების კატეგორიები",
        items: [
          { en: "Phone numbers and account identifiers.", ka: "ტელეფონის ნომრები და ანგარიშის იდენტიფიკატორები." },
          { en: "Bank account details required for payout execution.", ka: "ბანკის ანგარიშის დეტალები, რომლებიც საჭიროა გატანის შესასრულებლად." },
          { en: "Payment and transaction records for compliance and reconciliation.", ka: "გადახდის და ტრანზაქციის ჩანაწერები შესაბამისობისა და შერიგებისთვის." }
        ]
      },
      {
        type: "list",
        titleEn: "How data is used",
        titleKa: "როგორ გამოიყენება მონაცემები",
        items: [
          { en: "To authenticate users and authorize access by fleet role.", ka: "მომხმარებლის ავთენტიფიკაციისა და ფლიტის როლით წვდომის დასადასტურებლად." },
          { en: "To process funding and payouts.", ka: "შევსებისა და გატანების დასამუშავებლად." },
          { en: "To meet legal, fraud-prevention, and accounting obligations.", ka: "სამართლებრივი, ანტი-თაღლითური და საბუღალტრო ვალდებულებების შესასრულებლად." }
        ]
      }
    ]
  },
  "/terms": {
    titleEn: "Terms and Conditions",
    titleKa: "წესები და პირობები",
    introEn:
      "By using ExpertPay, users agree to use the service only for lawful business and payment operations approved by the fleet and the merchant.",
    introKa:
      "ExpertPay-ის გამოყენებით, მომხმარებელი ეთანხმება, რომ სერვისს გამოიყენებს მხოლოდ კანონიერი ბიზნესისა და გადახდის ოპერაციებისთვის, რომლებიც დამტკიცებულია ფლიტისა და მერჩანტის მიერ.",
    blocks: [
      {
        type: "list",
        titleEn: "Key terms",
        titleKa: "ძირითადი პირობები",
        items: [
          { en: "Users must provide accurate account and identity information.", ka: "მომხმარებელმა უნდა წარმოადგინოს ზუსტი ანგარიშისა და იდენტობის ინფორმაცია." },
          { en: "The merchant may suspend or review suspicious transactions.", ka: "მერჩანტს შეუძლია საეჭვო ტრანზაქციების შეჩერება ან განხილვა." },
          { en: "Processing times may depend on the bank, payment rail, verification, and operational review.", ka: "დამუშავების დრო შეიძლება დამოკიდებული იყოს ბანკზე, გადახდის არხზე, ვერიფიკაციასა და ოპერაციულ განხილვაზე." }
        ]
      }
    ]
  }
};

function renderBlock(block: SectionBlock, pick: (en: string, ka: string) => string) {
  if (block.type === "paragraph") {
    return <p className="publicBodyText">{pick(block.en, block.ka)}</p>;
  }

  if (block.type === "facts") {
    return (
      <div className="publicFactsGrid">
        {block.items.map((item) => (
          <div key={item.labelEn} className="card publicFactCard">
            <div className="publicFactLabel">{pick(item.labelEn, item.labelKa)}</div>
            <div className="publicFactValue">{item.value}</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <section className="publicSectionBlock">
      {block.titleEn ? <h2 className="publicSectionTitle">{pick(block.titleEn, block.titleKa ?? block.titleEn)}</h2> : null}
      <ul className="publicList">
        {block.items.map((item) => (
          <li key={item.en}>{pick(item.en, item.ka)}</li>
        ))}
      </ul>
    </section>
  );
}

export default function PublicInfoPage() {
  const { pick } = useI18n();
  const location = useLocation();

  const page = useMemo(() => CONTENT[location.pathname] ?? CONTENT["/service"], [location.pathname]);

  return (
    <section className="publicContent">
      <div className="card publicHeroCard">
        <div className="ownerHeroEyebrow">{pick("Bank Review Ready Pages", "ბანკის შემოწმებისთვის მზადყოფნის გვერდები")}</div>
        <h1 className="publicHeroTitle">{pick(page.titleEn, page.titleKa)}</h1>
        <p className="publicBodyText">{pick(page.introEn, page.introKa)}</p>
      </div>

      {page.blocks.map((block, index) => (
        <div key={`${location.pathname}-${index}`} className="card publicSectionCard">
          {renderBlock(block, pick)}
        </div>
      ))}
    </section>
  );
}
