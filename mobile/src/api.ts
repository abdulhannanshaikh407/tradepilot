import AsyncStorage from "@react-native-async-storage/async-storage";

import type { AutoTradeConfig, AutoTradeStatus, AuthResponse, BrokerConnection, BrokerAccount, DashboardStats, NotificationItem, Position, Signal, Strategy, User } from "./types";

const API_URL = (process.env.EXPO_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const TOKEN_KEY = "tp_token";

let token: string | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function loadToken(): Promise<string | null> {
  token = await AsyncStorage.getItem(TOKEN_KEY);
  return token;
}

export function getToken(): string | null {
  return token;
}

export async function setToken(value: string | null): Promise<void> {
  token = value;
  if (value) {
    await AsyncStorage.setItem(TOKEN_KEY, value);
  } else {
    await AsyncStorage.removeItem(TOKEN_KEY);
  }
}

export function baseUrl(): string {
  return API_URL;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your API URL and internet connection.");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  baseUrl,
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  signup: (email: string, password: string, name: string) =>
    request<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password, name }) }),
  demo: () => request<AuthResponse>("/auth/demo", { method: "POST" }),
  me: () => request<User>("/auth/me"),
  dashboard: () => request<DashboardStats>("/dashboard/stats"),
  strategies: () => request<Strategy[]>("/strategies"),
  signals: () => request<Signal[]>("/signals?limit=50"),
  notifications: () => request<NotificationItem[]>("/notifications"),
  autotradeStatus: () => request<AutoTradeStatus>("/autotrade/status"),
  autotradeConfigs: () => request<AutoTradeConfig[]>("/autotrade/config"),
  autotradeCreateConfig: (body: Partial<AutoTradeConfig>) =>
    request<AutoTradeConfig>("/autotrade/config", { method: "POST", body: JSON.stringify(body) }),
  autotradeUpdateConfig: (strategyId: number, body: Partial<AutoTradeConfig>) =>
    request<AutoTradeConfig>(`/autotrade/config/${strategyId}`, { method: "PATCH", body: JSON.stringify(body) }),
  runNow: () => request<{ configs: number; last_run_at?: string }>("/autotrade/run-now", { method: "POST" }),
  positions: () => request<Position[]>("/autotrade/positions"),
  closePosition: (id: number) =>
    request<Position>(`/autotrade/positions/${id}/close`, { method: "POST" }),
  registerDevice: (body: { token: string; platform: string }) =>
    request<{ id: number; message: string }>("/devices/register", { method: "POST", body: JSON.stringify(body) }),
  testPush: () => request<{ message: string }>("/devices/test-push", { method: "POST" }),
  // Broker connections
  connectBroker: (body: { broker: string; api_key: string; api_secret: string; account_type: string }) =>
    request<{ connection_id: number; broker: string; account_type: string; is_verified: boolean }>(
      "/brokers/connect", { method: "POST", body: JSON.stringify(body) }
    ),
  getConnectedBrokers: () => request<BrokerConnection[]>("/brokers/connected"),
  getBrokerAccount: (connectionId: number) =>
    request<BrokerAccount>(`/brokers/${connectionId}/account`),
  getBrokerPositions: (connectionId: number) =>
    request<{ symbol: string; quantity: number; entry_price: number; current_price: number; pnl: number; pnl_percent: number }[]>(
      `/brokers/${connectionId}/positions`
    ),
  disconnectBroker: (connectionId: number) =>
    request<void>(`/brokers/${connectionId}`, { method: "DELETE" }),
};