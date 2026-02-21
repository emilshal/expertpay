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
