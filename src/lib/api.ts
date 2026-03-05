const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const ACCESS_TOKEN_KEY = "expertpay_access_token";
const REFRESH_TOKEN_KEY = "expertpay_refresh_token";

type Json = Record<string, unknown>;

function buildUrl(path: string) {
  return `${API_BASE}${path}`;
}

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function setAuthTokens(access: string, refresh: string) {
  setTokens(access, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const response = await fetch(buildUrl("/api/auth/refresh/"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh })
  });

  if (!response.ok) {
    clearTokens();
    return null;
  }

  const payload = (await response.json()) as { access: string; refresh?: string };
  setTokens(payload.access, payload.refresh ?? refresh);
  return payload.access;
}

async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean; idempotent?: boolean } = {}
): Promise<T> {
  const { auth = true, idempotent = false, ...rest } = options;
  const headers = new Headers(rest.headers ?? {});
  headers.set("Content-Type", "application/json");

  if (idempotent) {
    headers.set("Idempotency-Key", crypto.randomUUID());
    headers.set("X-Request-ID", crypto.randomUUID());
  }

  if (auth) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response = await fetch(buildUrl(path), { ...rest, headers });

  if (response.status === 401 && auth) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      headers.set("Authorization", `Bearer ${refreshedToken}`);
      response = await fetch(buildUrl(path), { ...rest, headers });
    }
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export type MeResponse = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
};

export type Fleet = {
  id: number;
  name: string;
};

export type WalletBalance = {
  balance: string;
  currency: string;
  updated_at: string;
};

export type TransactionFeedItem = {
  id: string;
  kind: string;
  amount: string;
  currency: string;
  status: string;
  description: string;
  created_at: string;
};

export type BankAccount = {
  id: number;
  bank_name: string;
  account_number: string;
  beneficiary_name: string;
  is_active: boolean;
  created_at: string;
};

export type WithdrawalItem = {
  id: number;
  amount: string;
  currency: string;
  status: "pending" | "processing" | "completed" | "failed";
  note: string;
  bank_account: BankAccount;
  created_at: string;
};

export type YandexConnection = {
  id: number;
  provider: string;
  external_account_id: string;
  status: string;
  config: Record<string, unknown>;
  created_at: string;
};

export type YandexEvent = {
  id: number;
  external_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  processed: boolean;
  created_at: string;
};

export type YandexConnectionTestResult = {
  ok: boolean;
  configured: boolean;
  mode: string;
  http_status: number | null;
  endpoint: string;
  detail: string;
  response?: unknown;
};

export type YandexLiveSyncResult = {
  ok: boolean;
  partial?: boolean;
  configured: boolean;
  detail: string;
  drivers: {
    http_status: number | null;
    fetched: number;
  };
  transactions: {
    http_status: number | null;
    fetched: number;
    stored_new_events: number;
    imported_count: number;
    imported_total: string;
  };
  errors: {
    drivers: unknown;
    transactions: unknown;
  };
};

export type BankSimPayout = {
  id: number;
  withdrawal_id: number;
  provider_payout_id: string;
  status: "accepted" | "processing" | "settled" | "failed" | "reversed";
  failure_reason: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ReconciliationSummary = {
  currency: string;
  wallet: {
    wallet_balance: string;
    ledger_balance: string;
    delta: string;
    status: "OK" | "MISMATCH";
  };
  yandex: {
    imported_events: number;
    imported_total: string;
    ledger_total: string;
    delta: string;
    status: "OK" | "MISMATCH";
  };
  withdrawals: {
    count: number;
    total: string;
    completed_total: string;
    pending_total: string;
    failed_total: string;
  };
  bank_simulator: {
    count: number;
    totals_by_status: Record<string, string>;
  };
  generated_at: string;
  overall_status: "OK" | "MISMATCH";
};

export async function register(input: {
  username: string;
  password: string;
  email?: string;
  first_name?: string;
  last_name?: string;
}) {
  return request<Json>("/api/auth/register/", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      username: input.username,
      password: input.password,
      email: input.email ?? "",
      first_name: input.first_name ?? "",
      last_name: input.last_name ?? ""
    })
  });
}

export async function login(username: string, password: string) {
  const payload = await request<{ access: string; refresh: string }>("/api/auth/login/", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ username, password })
  });
  setTokens(payload.access, payload.refresh);
  return payload;
}

export async function me() {
  return request<MeResponse>("/api/auth/me/");
}

export async function fleets() {
  return request<Fleet[]>("/api/auth/fleets/", { auth: false });
}

export async function requestFleetCode(input: { fleet_name: string; phone_number: string }) {
  return request<{ challenge_id: number; expires_in_seconds: number; code?: string }>(
    "/api/auth/request-code/?debug=1",
    {
      method: "POST",
      auth: false,
      body: JSON.stringify(input)
    }
  );
}

export async function verifyFleetCode(input: { challenge_id: number; code: string }) {
  const payload = await request<{ access: string; refresh: string; user: MeResponse }>(
    "/api/auth/verify-code/",
    {
      method: "POST",
      auth: false,
      body: JSON.stringify(input)
    }
  );
  setTokens(payload.access, payload.refresh);
  return payload;
}

export async function walletBalance() {
  return request<WalletBalance>("/api/wallet/balance/");
}

export async function walletTransactions() {
  return request<TransactionFeedItem[]>("/api/wallet/transactions/");
}

export async function bankAccounts() {
  return request<BankAccount[]>("/api/wallet/bank-accounts/");
}

export async function createBankAccount(input: {
  bank_name: string;
  account_number: string;
  beneficiary_name: string;
}) {
  return request<BankAccount>("/api/wallet/bank-accounts/", {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function createWithdrawal(input: { bank_account_id: number; amount: string; note?: string }) {
  return request<Json>("/api/wallet/withdrawals/", {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function topUpWallet(input: { amount: string; note?: string }) {
  return request<{ balance: string; currency: string; credited_amount: string }>("/api/wallet/top-up/", {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function withdrawalsList() {
  return request<WithdrawalItem[]>("/api/wallet/withdrawals/list/");
}

export async function createInternalTransfer(input: {
  receiver_username: string;
  amount: string;
  note?: string;
}) {
  return request<Json>("/api/transfers/internal/", {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function createInternalTransferByBank(input: {
  bank_name: string;
  account_number: string;
  beneficiary_name: string;
  amount: string;
  note?: string;
}) {
  return request<Json>("/api/transfers/internal/by-bank/", {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function connectYandex() {
  return request<YandexConnection>("/api/integrations/yandex/connect/", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function testYandexConnection() {
  return request<{ connection: YandexConnection; test: YandexConnectionTestResult }>(
    "/api/integrations/yandex/test-connection/",
    {
      method: "POST",
      body: JSON.stringify({}),
      idempotent: true
    }
  );
}

export async function syncLiveYandex(input?: { limit?: number; dry_run?: boolean }) {
  return request<{ connection: YandexConnection; sync: YandexLiveSyncResult }>(
    "/api/integrations/yandex/sync-live/",
    {
      method: "POST",
      body: JSON.stringify({
        limit: input?.limit ?? 100,
        dry_run: input?.dry_run ?? false
      }),
      idempotent: true
    }
  );
}

export async function simulateYandexEvents(input: {
  mode: "steady" | "spiky" | "adjustment" | "duplicates" | "out_of_order";
  count: number;
}) {
  return request<{ connection_id: number; mode: string; requested_count: number; stored_count: number }>(
    "/api/integrations/yandex/simulate-events/",
    {
      method: "POST",
      body: JSON.stringify(input),
      idempotent: true
    }
  );
}

export async function importYandexEvents() {
  return request<{ imported_count: number; imported_total: string }>("/api/integrations/yandex/import/", {
    method: "POST",
    body: JSON.stringify({}),
    idempotent: true
  });
}

export async function reconcileYandex() {
  return request<{
    imported_events: number;
    imported_total: string;
    ledger_total: string;
    delta: string;
    status: "OK" | "MISMATCH";
  }>("/api/integrations/yandex/reconcile/");
}

export async function yandexEvents() {
  return request<YandexEvent[]>("/api/integrations/yandex/events/");
}

export async function connectBankSimulator() {
  return request<Json>("/api/integrations/bank-sim/connect/", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function bankSimulatorPayouts() {
  return request<BankSimPayout[]>("/api/integrations/bank-sim/payouts/");
}

export async function submitBankSimulatorPayout(withdrawal_id: number) {
  return request<BankSimPayout>("/api/integrations/bank-sim/payouts/submit/", {
    method: "POST",
    body: JSON.stringify({ withdrawal_id }),
    idempotent: true
  });
}

export async function updateBankSimulatorPayoutStatus(
  payout_id: number,
  input: { status: "accepted" | "processing" | "settled" | "failed" | "reversed"; failure_reason?: string }
) {
  return request<BankSimPayout>(`/api/integrations/bank-sim/payouts/${payout_id}/status/`, {
    method: "POST",
    body: JSON.stringify(input),
    idempotent: true
  });
}

export async function reconciliationSummary() {
  return request<ReconciliationSummary>("/api/integrations/reconciliation/summary/");
}
