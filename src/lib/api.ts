const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const ACCESS_TOKEN_KEY = "expertpay_access_token";
const REFRESH_TOKEN_KEY = "expertpay_refresh_token";
const ACTIVE_FLEET_NAME_KEY = "expertpay_active_fleet_name";

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

export function setActiveFleetName(name: string) {
  localStorage.setItem(ACTIVE_FLEET_NAME_KEY, name);
}

export function getActiveFleetName() {
  return localStorage.getItem(ACTIVE_FLEET_NAME_KEY);
}

export function setAuthTokens(access: string, refresh: string) {
  setTokens(access, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(ACTIVE_FLEET_NAME_KEY);
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
    const fleetName = getActiveFleetName();
    if (fleetName) headers.set("X-Fleet-Name", fleetName);
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

export type FleetMember = {
  id: number;
  fleet: number;
  username: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  role: "driver" | "operator" | "admin" | "owner";
  is_active: boolean;
  created_at: string;
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
  beneficiary_inn: string;
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
    upserted_profiles?: number;
  };
  transactions: {
    http_status: number | null;
    fetched: number;
    stored_new_events: number;
    imported_count: number;
    imported_total: string;
  };
  cursor?: {
    from: string;
    to: string;
    next_from: string;
    full_sync: boolean;
  };
  errors: {
    drivers: unknown;
    transactions: unknown;
  };
};

export type YandexCategory = {
  id: number;
  external_category_id: string;
  code: string;
  name: string;
  is_creatable: boolean;
  is_enabled: boolean;
  updated_at: string;
};

export type YandexDriverProfile = {
  id: number;
  external_driver_id: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  status: string;
  updated_at: string;
};

export type YandexTransactionRecord = {
  id: number;
  external_transaction_id: string;
  driver_external_id: string;
  event_at: string | null;
  amount: string;
  currency: string;
  category: string;
  direction: string;
  updated_at: string;
};

export type YandexDriverSummary = {
  driver: YandexDriverProfile;
  summary: {
    transaction_count: number;
    total_earned: string;
    total_deductions: string;
    net_total: string;
    last_transaction_at: string | null;
    currency: string;
  };
};

export type YandexDriverDetail = {
  driver: YandexDriverProfile;
  summary: {
    transaction_count: number;
    total_earned: string;
    total_deductions: string;
    net_total: string;
    last_transaction_at: string | null;
    currency: string;
  };
  recent_transactions: YandexTransactionRecord[];
};

export type YandexSyncRun = {
  id: number;
  trigger: "api" | "scheduler";
  status: "ok" | "partial" | "error";
  dry_run: boolean;
  full_sync: boolean;
  drivers_http_status: number | null;
  transactions_http_status: number | null;
  drivers_fetched: number;
  drivers_upserted: number;
  transactions_fetched: number;
  transactions_stored_new: number;
  imported_count: number;
  imported_total: string;
  cursor_from: string | null;
  cursor_to: string | null;
  cursor_next_from: string | null;
  detail: string;
  started_at: string;
  completed_at: string;
  created_at: string;
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

export type BogPayout = {
  id: number;
  withdrawal_id: number;
  provider_unique_id: string;
  provider_unique_key: number | null;
  status: "accepted" | "processing" | "settled" | "failed" | "reversed";
  provider_status: string;
  result_code: number | null;
  match_score: string | null;
  failure_reason: string;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  submitted_at: string;
  last_status_checked_at: string | null;
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
    last_connection_test?: {
      ok: boolean;
      checked_at: string;
      http_status: number | null;
      detail: string;
    } | null;
    last_live_sync?: {
      ok: boolean;
      partial?: boolean;
      checked_at: string;
      drivers_fetched: number;
      drivers_upserted?: number;
      transactions_fetched: number;
      imported_count: number;
      imported_total?: string;
      detail?: string;
    } | null;
    last_category_sync?: {
      ok: boolean;
      checked_at: string;
      fetched: number;
      upserted: number;
      http_status: number | null;
    } | null;
    last_transaction_cursor?: {
      from: string;
      to: string;
      next_from: string;
      full_sync: boolean;
    } | null;
    stored_driver_profiles?: number;
    stored_transactions?: number;
    stored_categories?: number;
    sync_runs_count?: number;
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
  bog: {
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
  const payload = await request<{ access: string; refresh: string; user: MeResponse; fleet?: Fleet; role?: string }>(
    "/api/auth/verify-code/",
    {
      method: "POST",
      auth: false,
      body: JSON.stringify(input)
    }
  );
  setTokens(payload.access, payload.refresh);
  if (payload.fleet?.name) setActiveFleetName(payload.fleet.name);
  return payload;
}

export async function fleetMembers(fleetName: string) {
  return request<FleetMember[]>(`/api/auth/fleet-members/?fleet_name=${encodeURIComponent(fleetName)}`);
}

export async function updateFleetMemberRole(input: {
  fleet_name: string;
  phone_number: string;
  role: "driver" | "operator" | "admin" | "owner";
}) {
  return request<FleetMember>("/api/auth/fleet-members/role/", {
    method: "PATCH",
    body: JSON.stringify(input),
    idempotent: true
  });
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
  beneficiary_inn?: string;
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

export async function syncLiveYandex(input?: { limit?: number; dry_run?: boolean; full_sync?: boolean }) {
  return request<{ connection: YandexConnection; sync: YandexLiveSyncResult }>(
    "/api/integrations/yandex/sync-live/",
    {
      method: "POST",
      body: JSON.stringify({
        limit: input?.limit ?? 100,
        dry_run: input?.dry_run ?? false,
        full_sync: input?.full_sync ?? false
      }),
      idempotent: true
    }
  );
}

export async function syncYandexCategories() {
  return request<{ connection: YandexConnection; categories_sync: Record<string, unknown> }>(
    "/api/integrations/yandex/sync-categories/",
    {
      method: "POST",
      body: JSON.stringify({}),
      idempotent: true
    }
  );
}

export async function yandexCategories() {
  return request<YandexCategory[]>("/api/integrations/yandex/categories/");
}

export async function yandexDrivers() {
  return request<YandexDriverProfile[]>("/api/integrations/yandex/drivers/");
}

export async function yandexDriverSummaries() {
  return request<YandexDriverSummary[]>("/api/integrations/yandex/driver-summaries/");
}

export async function yandexDriverDetail(externalDriverId: string) {
  return request<YandexDriverDetail>(`/api/integrations/yandex/drivers/${encodeURIComponent(externalDriverId)}/`);
}

export async function yandexTransactions() {
  return request<YandexTransactionRecord[]>("/api/integrations/yandex/transactions/");
}

export async function yandexSyncRuns() {
  return request<YandexSyncRun[]>("/api/integrations/yandex/sync-runs/");
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

export async function testBogToken() {
  return request<{ connection: YandexConnection; test: Record<string, unknown> }>("/api/integrations/bog/test-token/", {
    method: "POST",
    body: JSON.stringify({}),
    idempotent: true
  });
}

export async function bogPayouts() {
  return request<BogPayout[]>("/api/integrations/bog/payouts/");
}

export async function submitBogPayout(withdrawal_id: number) {
  return request<BogPayout>("/api/integrations/bog/payouts/submit/", {
    method: "POST",
    body: JSON.stringify({ withdrawal_id }),
    idempotent: true
  });
}

export async function syncBogPayoutStatus(payout_id: number) {
  return request<BogPayout>(`/api/integrations/bog/payouts/${payout_id}/status/`, {
    method: "POST",
    body: JSON.stringify({}),
    idempotent: true
  });
}

export async function syncAllBogPayoutStatuses() {
  return request<{ checked_count: number; updated_count: number; error_count: number; errors: unknown[] }>(
    "/api/integrations/bog/payouts/sync-all/",
    {
      method: "POST",
      body: JSON.stringify({}),
      idempotent: true
    }
  );
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
