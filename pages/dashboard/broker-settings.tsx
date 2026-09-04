import React, { useEffect, useState } from "react";
import Head from "next/head";

import DashboardPage from "components/DashboardPage";
import { Button, Card, Skeleton, useToast } from "components/ui";
import { api, ApiError, formatNumber } from "lib/api";

interface BrokerConn {
  id: number;
  broker: string;
  account_type: string;
  is_verified: boolean;
  last_verified_at?: string | null;
  created_at?: string | null;
}

interface BrokerAccountData {
  balance: number;
  buying_power: number;
  cash: number;
  account_type: string;
  broker_name: string;
  daily_pnl: number;
  daily_pnl_percent: number;
  positions: {
    symbol: string;
    quantity: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    pnl_percent: number;
  }[];
}

const BROKERS = [
  { key: "alpaca", label: "Alpaca (Stocks)", accountTypes: ["paper", "live"] },
  { key: "binance", label: "Binance (Crypto)", accountTypes: ["live"] },
  { key: "oanda", label: "OANDA (Forex & Metals)", accountTypes: ["practice", "live"] },
];

export default function BrokerSettingsPage() {
  const { toast } = useToast();
  const [connections, setConnections] = useState<BrokerConn[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBroker, setSelectedBroker] = useState("alpaca");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountId, setAccountId] = useState("");
  const [accountType, setAccountType] = useState("paper");
  const [connecting, setConnecting] = useState(false);
  const [accountData, setAccountData] = useState<BrokerAccountData | null>(null);
  const [selectedConnId, setSelectedConnId] = useState<number | null>(null);

  const loadConnections = async () => {
    try {
      const result = await api<BrokerConn[]>("/brokers/connected");
      setConnections(result);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConnections();
  }, []);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey || !apiSecret) {
      toast("API key and secret are required.", "error");
      return;
    }

    const brokerConfig = BROKERS.find((b) => b.key === selectedBroker);
    if (brokerConfig && !brokerConfig.accountTypes.includes(accountType)) {
      toast(`${brokerConfig.label} only supports ${brokerConfig.accountTypes.join(" or ")} accounts.`, "error");
      return;
    }

    setConnecting(true);
    try {
      const body: Record<string, string> = { broker: selectedBroker, api_key: apiKey, api_secret: apiSecret, account_type: accountType };
      if (selectedBroker === "oanda" && accountId) {
        body.account_id = accountId;
      }
      await api("/brokers/connect", {
        method: "POST",
        body,
      });
      toast(`Connected to ${selectedBroker.toUpperCase()}`, "success");
      setApiKey("");
      setApiSecret("");
      setAccountId("");
      loadConnections();
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Connection failed", "error");
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async (connId: number) => {
    if (!confirm("Remove this broker connection?")) return;
    try {
      await api(`/brokers/${connId}`, { method: "DELETE" });
      toast("Broker disconnected", "success");
      loadConnections();
      if (selectedConnId === connId) {
        setAccountData(null);
        setSelectedConnId(null);
      }
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Disconnect failed", "error");
    }
  };

  const viewAccount = async (connId: number) => {
    try {
      const data = await api<BrokerAccountData>(`/brokers/${connId}/account`);
      setAccountData(data);
      setSelectedConnId(connId);
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Failed to fetch account", "error");
    }
  };

  return (
    <DashboardPage>
      <Head>
        <title>Broker Settings — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Broker Settings</h1>
        <p className="text-xs text-slate-500">Connect your broker accounts for real trading.</p>
      </div>

      {loading ? (
        <div className="space-y-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : (
        <div className="grid max-w-3xl gap-6">
          {/* Connect Form */}
          <Card title="Connect Broker">
            <form onSubmit={handleConnect} className="space-y-4">
              <div>
                <label className="label">Broker</label>
                <div className="flex gap-2">
                  {BROKERS.map((b) => (
                    <button
                      key={b.key}
                      type="button"
                      onClick={() => {
                        setSelectedBroker(b.key);
                        setAccountType(b.accountTypes[0]);
                      }}
                      className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                        selectedBroker === b.key
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                      }`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Account Type</label>
                <div className="flex gap-2">
                  {BROKERS.find((b) => b.key === selectedBroker)?.accountTypes.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setAccountType(t)}
                      className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                        accountType === t
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                      }`}
                    >
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {accountType === "live" && (
                <div className="rounded-lg border border-amber-700/30 bg-amber-900/20 p-3 text-xs text-amber-300">
                  LIVE TRADING ENABLED — Real money will be used. Only continue if you understand the risks and have
                  tested your strategy extensively.
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">API Key</label>
                  <input
                    className="input font-mono"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter API key"
                    required
                  />
                </div>
                <div>
                  <label className="label">API Secret</label>
                  <input
                    className="input font-mono"
                    type="password"
                    value={apiSecret}
                    onChange={(e) => setApiSecret(e.target.value)}
                    placeholder="Enter API secret"
                    required
                  />
                </div>
              </div>

              {selectedBroker === "oanda" && (
                <div>
                  <label className="label">OANDA Account ID</label>
                  <input
                    className="input font-mono"
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    placeholder="e.g. 101-001-12345678-001"
                    required
                  />
                </div>
              )}

              <div className="flex justify-end">
                <Button type="submit" loading={connecting}>
                  Connect {selectedBroker.toUpperCase()}
                </Button>
              </div>
            </form>
          </Card>

          {/* Connected Brokers */}
          <Card title="Connected Brokers">
            {connections.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-500">No brokers connected yet.</p>
            ) : (
              <div className="space-y-3">
                {connections.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 p-3"
                  >
                    <div>
                      <span className="font-semibold text-white">{c.broker.toUpperCase()}</span>
                      <span className="ml-2 text-xs text-slate-500">{c.account_type}</span>
                      {c.is_verified && (
                        <span className="ml-2 rounded bg-emerald-900/30 px-2 py-0.5 text-[10px] text-emerald-400">
                          Verified
                        </span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button variant="ghost" onClick={() => viewAccount(c.id)}>
                        View Account
                      </Button>
                      <Button variant="ghost" onClick={() => handleDisconnect(c.id)}>
                        Disconnect
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Account Details */}
          {accountData && (
            <Card title="Account Details">
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <p className="text-[11px] text-slate-500">Balance</p>
                  <p className="text-lg font-bold text-white">${formatNumber(accountData.balance)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">Buying Power</p>
                  <p className="text-lg font-bold text-white">${formatNumber(accountData.buying_power)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">Cash</p>
                  <p className="text-lg font-bold text-white">${formatNumber(accountData.cash)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">Daily P&L</p>
                  <p className={`text-lg font-bold ${accountData.daily_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    ${formatNumber(accountData.daily_pnl)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">Broker</p>
                  <p className="text-sm text-white">{accountData.broker_name}</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500">Type</p>
                  <p className="text-sm text-white">{accountData.account_type}</p>
                </div>
              </div>

              {accountData.positions.length > 0 && (
                <div className="mt-6">
                  <h3 className="mb-3 text-sm font-semibold text-white">Open Positions</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-800 text-left text-xs text-slate-500">
                          <th className="pb-2">Symbol</th>
                          <th className="pb-2">Qty</th>
                          <th className="pb-2">Entry</th>
                          <th className="pb-2">Current</th>
                          <th className="pb-2">P&L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {accountData.positions.map((p, i) => (
                          <tr key={i} className="border-b border-slate-800/50">
                            <td className="py-2 font-medium text-white">{p.symbol}</td>
                            <td className="py-2 text-slate-400">{p.quantity.toFixed(4)}</td>
                            <td className="py-2 text-slate-400">${formatNumber(p.entry_price)}</td>
                            <td className="py-2 text-slate-400">${formatNumber(p.current_price)}</td>
                            <td className={`py-2 font-medium ${p.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                              ${formatNumber(p.pnl)} ({p.pnl_percent.toFixed(2)}%)
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </DashboardPage>
  );
}
