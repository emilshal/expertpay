import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearTokens,
  getAccessToken,
  getActiveFleetName,
  getActiveRole,
  getIsPlatformAdmin,
  login,
  me,
  setActiveFleetName,
  setActiveRole,
  setAuthTokens,
  setIsPlatformAdmin,
  verifyFleetCode,
} from "../src/lib/api";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length() {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("auth session storage normalization", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", new MemoryStorage());
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clears stale fleet keys when me() returns a platform-admin-only profile", async () => {
    setAuthTokens("access-token", "refresh-token");
    setActiveFleetName("Old Fleet");
    setActiveRole("owner");

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: 10,
        username: "platform-admin",
        first_name: "Platform",
        last_name: "Admin",
        email: "admin@example.com",
        fleet: null,
        role: null,
        is_platform_admin: true,
      }),
    );

    await me();

    expect(getActiveFleetName()).toBeNull();
    expect(getActiveRole()).toBeNull();
    expect(getIsPlatformAdmin()).toBe(true);
  });

  it("clears stale fleet UI state during login before a platform-admin profile refresh", async () => {
    setActiveFleetName("Fleet That Should Not Persist");
    setActiveRole("operator");
    setIsPlatformAdmin(true);

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        access: "new-access",
        refresh: "new-refresh",
      }),
    );

    await login("platform-admin", "pass1234");

    expect(getAccessToken()).toBe("new-access");
    expect(getActiveFleetName()).toBeNull();
    expect(getActiveRole()).toBeNull();
    expect(getIsPlatformAdmin()).toBe(false);
  });

  it("stores the correct fleet name and role for a fleet user login flow", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        access: "fleet-access",
        refresh: "fleet-refresh",
        fleet: { id: 7, name: "Fleet Seven" },
        role: "admin",
        user: {
          id: 22,
          username: "fleet-admin",
          first_name: "Fleet",
          last_name: "Admin",
          email: "fleet@example.com",
          fleet: { id: 7, name: "Fleet Seven" },
          role: "admin",
          is_platform_admin: false,
        },
      }),
    );

    await verifyFleetCode({ challenge_id: 1, code: "1234" });

    expect(getActiveFleetName()).toBe("Fleet Seven");
    expect(getActiveRole()).toBe("admin");
    expect(getIsPlatformAdmin()).toBe(false);
  });

  it("clearTokens removes both fleet and platform-admin session state", () => {
    setAuthTokens("access-token", "refresh-token");
    setActiveFleetName("Fleet Before Logout");
    setActiveRole("driver");
    setIsPlatformAdmin(true);

    clearTokens();

    expect(getAccessToken()).toBeNull();
    expect(getActiveFleetName()).toBeNull();
    expect(getActiveRole()).toBeNull();
    expect(getIsPlatformAdmin()).toBe(false);
  });
});
