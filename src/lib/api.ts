const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

const ACCESS_TOKEN_KEY = "expertpay_access_token";
const REFRESH_TOKEN_KEY = "expertpay_refresh_token";
const ACTIVE_FLEET_NAME_KEY = "expertpay_active_fleet_name";
const ACTIVE_ROLE_KEY = "expertpay_active_role";
const PLATFORM_ADMIN_KEY = "expertpay_platform_admin";

type SessionRole = "driver" | "operator" | "admin" | "owner";

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

export function setActiveRole(role: SessionRole) {
  localStorage.setItem(ACTIVE_ROLE_KEY, role);
}

export function getActiveRole() {
  return localStorage.getItem(ACTIVE_ROLE_KEY) as SessionRole | null;
}

export function setIsPlatformAdmin(isPlatformAdmin: boolean) {
  if (isPlatformAdmin) {
    localStorage.setItem(PLATFORM_ADMIN_KEY, "true");
    return;
  }
  localStorage.removeItem(PLATFORM_ADMIN_KEY);
}

export function getIsPlatformAdmin() {
  return localStorage.getItem(PLATFORM_ADMIN_KEY) === "true";
}

export function setAuthTokens(access: string, refresh: string) {
  setTokens(access, refresh);
}

function clearFleetSessionState() {
  localStorage.removeItem(ACTIVE_FLEET_NAME_KEY);
  localStorage.removeItem(ACTIVE_ROLE_KEY);
}

type SessionPayload = {
  fleet?: Fleet | null;
  role?: SessionRole | null;
  is_platform_admin?: boolean | null;
};

export function applyAuthSession(payload: SessionPayload) {
  if (payload.fleet?.name) {
    setActiveFleetName(payload.fleet.name);
  } else {
    localStorage.removeItem(ACTIVE_FLEET_NAME_KEY);
  }

  if (payload.role) {
    setActiveRole(payload.role);
  } else {
    localStorage.removeItem(ACTIVE_ROLE_KEY);
  }

  setIsPlatformAdmin(Boolean(payload.is_platform_admin));
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  clearFleetSessionState();
  localStorage.removeItem(PLATFORM_ADMIN_KEY);
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
  fleet: Fleet | null;
  role: "driver" | "operator" | "admin" | "owner" | null;
  is_platform_admin?: boolean;
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

export type DriverYandexMapping = {
  id: number;
  fleet: number;
  user_id: number;
  username: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  role: "driver";
  is_active: boolean;
  has_mapping: boolean;
  yandex_external_driver_id: string;
  mapping_conflict: boolean;
  mapping_conflict_fleet_name?: string | null;
};

export type WalletBalance = {
  balance: string;
  currency: string;
  updated_at: string;
  fleet_rating?: string;
  fleet_completed_withdrawals?: number;
  driver_name?: string;
  driver_level?: number;
  driver_reward?: string;
};

export type DepositInstruction = {
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  currency: string;
  fleet_name: string;
  reference_code: string;
  note: string;
};

export type DepositItem = {
  id: number;
  amount: string;
  currency: string;
  status: "completed" | "failed";
  fleet_name?: string;
  reference_code: string;
  provider: string;
  provider_transaction_id: string;
  payer_name: string;
  payer_inn: string;
  payer_account_number: string;
  note: string;
  sync_source?: "activity_poll" | "backfill";
  completed_at: string;
  created_at: string;
};

export type IncomingBankTransferItem = {
  id: number;
  provider: string;
  provider_transaction_id: string;
  account_number: string;
  currency: string;
  amount: string;
  fleet_name?: string;
  reference_text: string;
  payer_name: string;
  payer_inn: string;
  payer_account_number: string;
  booking_date: string | null;
  value_date: string | null;
  match_status: "matched" | "unmatched" | "ignored";
  sync_source?: "activity_poll" | "backfill";
  created_at: string;
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
  fee_amount: string;
  currency: string;
  status: "pending" | "processing" | "completed" | "failed";
  note: string;
  fleet_name?: string;
  driver_name: string;
  bank_account: BankAccount;
  created_at: string;
};

export type OwnerPendingPayout = {
  id: number;
  driver_name: string;
  driver_username: string;
  amount: string;
  fee_amount: string;
  currency: string;
  status: "pending" | "processing" | "completed" | "failed";
  created_at: string;
};

export type OwnerFleetSummary = {
  fleet_name: string;
  currency: string;
  reserve_balance: string;
  total_funded: string;
  total_withdrawn: string;
  total_fees: string;
  pending_payouts_count: number;
  pending_payouts_total: string;
  unmatched_deposits_count: number;
  failed_payouts_count: number;
  failed_payouts_total: string;
  active_drivers_count: number;
  pending_payouts: OwnerPendingPayout[];
};

export type OwnerDriverFinanceRow = {
  id: number;
  first_name: string;
  last_name: string;
  phone_number: string;
  transaction_count: number;
  available_balance: string;
  currency: string;
  created_at: string;
};

export type OwnerTransactionRow = {
  id: string;
  transaction_type: string;
  amount: string;
  currency: string;
  created_at: string;
};

export type AdminWithdrawnFleetItem = {
  fleet_id: number;
  fleet_name: string;
  transaction_count: number;
  total_withdrawn: string;
};

export type AdminPendingFleetItem = {
  fleet_id: number;
  fleet_name: string;
  transaction_count: number;
  pending_total: string;
  reserve_balance: string;
};

export type AdminNetworkSummary = {
  currency: string;
  total_funded: string;
  total_withdrawn: string;
  total_fees: string;
  pending_payouts_count: number;
  pending_payouts_total: string;
  fleet_count: number;
  active_fleet_count: number;
  completed_withdrawal_transactions: number;
  withdrawn_by_fleet: AdminWithdrawnFleetItem[];
  pending_by_fleet: AdminPendingFleetItem[];
};

export type PlatformEarningsFleetItem = {
  fleet_id: number;
  fleet_name: string;
  total_fees_earned: string;
};

export type PlatformEarningsSummary = {
  currency: string;
  total_fees_earned: string;
  recent_totals: {
    last_7_days: string;
    last_30_days: string;
  };
  fees_by_fleet: PlatformEarningsFleetItem[];
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

export type BogPayoutActionResult = {
  detail: string;
  payout: BogPayout;
};

export type BogCardOrder = {
  id: number;
  fleet_name?: string;
  provider_order_id: string;
  external_order_id: string;
  parent_order_id: string;
  amount: string;
  currency: string;
  status: "created" | "pending" | "completed" | "failed" | "cancelled";
  provider_order_status: string;
  redirect_url: string;
  details_url: string;
  callback_url: string;
  success_url: string;
  fail_url: string;
  save_card: boolean;
  transaction_id: string;
  payer_identifier: string;
  transfer_method: string;
  card_type: string;
  callback_received_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReconciliationSummary = {
  currency: string;
  treasury: {
    balance: string;
    expected_total: string;
    delta: string;
    status: "OK" | "MISMATCH";
  };
  fleet_reserves: {
    account_count: number;
    total_balance: string;
  };
  driver_available: {
    account_count: number;
    total_balance: string;
  };
  payout_clearing: {
    balance: string;
    pending_withdrawals_count: number;
    pending_withdrawals_total: string;
  };
  platform_fees: {
    balance: string;
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
  deposits: {
    matched_count: number;
    matched_total: string;
    unmatched_count: number;
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
  applyAuthSession({ fleet: null, role: null, is_platform_admin: false });
  return payload;
}

export async function me() {
  const payload = await request<MeResponse>("/api/auth/me/");
  applyAuthSession(payload);
  return payload;
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
  applyAuthSession({
    fleet: payload.fleet ?? payload.user?.fleet ?? null,
    role: (payload.role as SessionRole | undefined) ?? payload.user?.role ?? null,
    is_platform_admin: payload.user?.is_platform_admin,
  });
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

export async function fleetDriverMappings(fleetName: string) {
  return request<DriverYandexMapping[]>(
    `/api/auth/driver-mappings/?fleet_name=${encodeURIComponent(fleetName)}`
  );
}

export async function updateFleetDriverMapping(input: {
  binding_id: number;
  fleet_name: string;
  yandex_external_driver_id: string;
}) {
  return request<DriverYandexMapping>(`/api/auth/driver-mappings/${input.binding_id}/`, {
    method: "PATCH",
    body: JSON.stringify({
      fleet_name: input.fleet_name,
      yandex_external_driver_id: input.yandex_external_driver_id
    }),
    idempotent: true
  });
}

export async function walletBalance() {
  return request<WalletBalance>("/api/wallet/balance/");
}

export async function ownerFleetSummary() {
  return request<OwnerFleetSummary>("/api/wallet/owner-summary/");
}

export async function ownerDriverFinanceRows() {
  return request<OwnerDriverFinanceRow[]>("/api/wallet/owner-driver-finance/");
}

export async function ownerTransactionRows() {
  return request<OwnerTransactionRow[]>("/api/wallet/owner-transactions/");
}

export async function adminNetworkSummary() {
  return request<AdminNetworkSummary>("/api/wallet/admin-network-summary/");
}

export async function platformEarningsSummary() {
  return request<PlatformEarningsSummary>("/api/integrations/platform/earnings/");
}

export async function depositInstructions() {
  return request<DepositInstruction>("/api/wallet/deposit-instructions/");
}

export async function depositsList() {
  return request<DepositItem[]>("/api/wallet/deposits/");
}

export async function syncDeposits(input?: { start_date?: string; end_date?: string }) {
  const payload: { start_date?: string; end_date?: string } = {};
  if (input?.start_date && input?.end_date) {
    payload.start_date = input.start_date;
    payload.end_date = input.end_date;
  }

  return request<{
    ok: boolean;
    configured: boolean;
    detail: string;
    checked_count: number;
    matched_count: number;
    credited_count: number;
    unmatched_count: number;
    ignored_count: number;
    credited_total: string;
    http_status: number | null;
    endpoint: string;
    sync_source?: "activity_poll" | "backfill";
    start_date?: string;
    end_date?: string;
    errors: unknown;
  }>("/api/wallet/deposits/sync/", {
    method: "POST",
    body: JSON.stringify(payload),
    idempotent: true
  });
}

export async function unmatchedIncomingTransfers() {
  return request<IncomingBankTransferItem[]>("/api/wallet/incoming-transfers/unmatched/");
}

export async function manualMatchIncomingTransfer(input: {
  transfer_id: number;
  fleet_name?: string;
}) {
  return request<{ transfer: IncomingBankTransferItem; deposit: DepositItem }>(
    `/api/wallet/incoming-transfers/${input.transfer_id}/match/`,
    {
      method: "POST",
      body: JSON.stringify({ fleet_name: input.fleet_name }),
      idempotent: true
    }
  );
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
  return request<WithdrawalItem>("/api/wallet/withdrawals/", {
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

export async function testBogPaymentsToken() {
  return request<{ connection: YandexConnection; test: Record<string, unknown> }>(
    "/api/integrations/bog-payments/test-token/",
    {
      method: "POST",
      body: JSON.stringify({}),
      idempotent: true
    }
  );
}

export async function bogCardOrders() {
  return request<BogCardOrder[]>("/api/integrations/bog-payments/orders/");
}

export async function createBogCardOrder(input: {
  amount: string;
  currency?: string;
  save_card?: boolean;
  parent_order_id?: string;
}) {
  return request<BogCardOrder>("/api/integrations/bog-payments/orders/create/", {
    method: "POST",
    body: JSON.stringify({
      amount: input.amount,
      currency: input.currency ?? "GEL",
      save_card: input.save_card ?? false,
      parent_order_id: input.parent_order_id ?? ""
    }),
    idempotent: true
  });
}

export async function syncBogCardOrder(providerOrderId: string) {
  return request<BogCardOrder>(
    `/api/integrations/bog-payments/orders/${encodeURIComponent(providerOrderId)}/sync/`,
    {
      method: "POST",
      body: JSON.stringify({}),
      idempotent: true
    }
  );
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

export async function requestBogPayoutOtp(payout_id: number) {
  return request<BogPayoutActionResult>(`/api/integrations/bog/payouts/${payout_id}/otp/request/`, {
    method: "POST",
    body: JSON.stringify({}),
    idempotent: true
  });
}

export async function signBogPayout(payout_id: number, otp: string) {
  return request<BogPayoutActionResult>(`/api/integrations/bog/payouts/${payout_id}/sign/`, {
    method: "POST",
    body: JSON.stringify({ otp }),
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
