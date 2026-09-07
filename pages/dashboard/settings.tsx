import React, { useEffect, useState } from "react";
import Head from "next/head";

import DashboardPage from "components/DashboardPage";
import { Button, Card, Skeleton, useToast } from "components/ui";
import { useAuth } from "lib/auth";
import { api, ApiError } from "lib/api";
import type { User as UserType } from "lib/types";

export default function Settings() {
  const { user, refreshUser } = useAuth();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [killSwitch, setKillSwitch] = useState(false);
  const [togglingKill, setTogglingKill] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
      setKillSwitch((user as any).kill_switch || false);
    }
    api<UserType>("/settings")
      .then((settings) => {
        const secret = (settings as any).webhook_secret || "";
        setWebhookSecret(secret);
      })
      .catch(() => {
        /* non-critical */
      });
  }, [user]);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api("/settings", { method: "PUT", body: { name, email } });
      await refreshUser();
      toast("Profile updated", "success");
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Update failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast("New passwords do not match", "error");
      return;
    }
    setChangingPassword(true);
    try {
      await api("/settings", {
        method: "PUT",
        body: { current_password: currentPassword, new_password: newPassword },
      });
      toast("Password updated", "success");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Password change failed", "error");
    } finally {
      setChangingPassword(false);
    }
  };

  const toggleKillSwitch = async () => {
    setTogglingKill(true);
    try {
      const result = await api<{ kill_switch: boolean; message: string }>("/settings/kill-switch", { method: "POST" });
      setKillSwitch(result.kill_switch);
      await refreshUser();
      toast(result.message, result.kill_switch ? "warning" : "success");
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Kill switch toggle failed", "error");
    } finally {
      setTogglingKill(false);
    }
  };

  return (
    <DashboardPage>
      <Head>
        <title>Settings — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="text-xs text-slate-500">Account, security and your workspace identity.</p>
      </div>

      {!user ? (
        <div className="space-y-6">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : (
        <div className="grid max-w-2xl gap-6">
          <Card title="Profile">
            <form onSubmit={saveProfile} className="space-y-4">
              <div>
                <label className="label">Name</label>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label className="label">Email</label>
                <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="flex items-center justify-between">
                <div className="text-[11px] text-slate-500">
                  Plan: <span className="font-semibold text-emerald-400">{user.plan}</span>
                  {user.is_demo && <span className="chip ml-2 bg-warn/15 text-amber-300">DEMO ACCOUNT</span>}
                </div>
                <Button type="submit" loading={saving}>Save changes</Button>
              </div>
            </form>
          </Card>

          <Card title="Security">
            <form onSubmit={changePassword} className="space-y-4">
              <div>
                <label className="label">Current password</label>
                <input className="input" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required autoComplete="current-password" />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">New password</label>
                  <input className="input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={8} autoComplete="new-password" />
                </div>
                <div>
                  <label className="label">Confirm new password</label>
                  <input className="input" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={8} autoComplete="new-password" />
                </div>
              </div>
              <div className="flex justify-end">
                <Button type="submit" variant="secondary" loading={changingPassword}>
                  Update password
                </Button>
              </div>
            </form>
          </Card>

          <Card title="Workspace">
            <div>
              <label className="label">Webhook secret</label>
              <div className="flex items-center gap-2">
                <input className="input font-mono text-[11px]" readOnly value={webhookSecret || "—"} />
                <Button
                  variant="ghost"
                  onClick={() => {
                    navigator.clipboard?.writeText(webhookSecret).then(
                      () => toast("Secret copied", "success"),
                      () => toast("Copy failed", "error")
                    );
                  }}
                >
                  Copy
                </Button>
              </div>
              <p className="mt-2 text-[11px] text-slate-600">
                Sent in TradingView webhook payloads as the <code className="font-mono">secret</code> field to attribute
                signals to this workspace. Manage the endpoint from the TradingView page.
              </p>
            </div>
          </Card>

          <Card title="Risk Management">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white font-medium">Kill Switch</p>
                <p className="text-[11px] text-slate-500 mt-1">
                  When enabled, blocks ALL live order execution across all strategies and brokers. 
                  Paper trading is unaffected. Signals will still be generated but no live trades will be placed.
                </p>
              </div>
              <button
                onClick={toggleKillSwitch}
                disabled={togglingKill}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  killSwitch ? "bg-red-500" : "bg-slate-600"
                } ${togglingKill ? "opacity-50" : "cursor-pointer"}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    killSwitch ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
            {killSwitch && (
              <div className="mt-3 p-2 rounded bg-red-500/10 border border-red-500/20">
                <p className="text-[11px] text-red-400 font-medium">
                  KILL SWITCH ACTIVE — All live trading is paused. No new live orders will be executed.
                </p>
              </div>
            )}
          </Card>
        </div>
      )}
    </DashboardPage>
  );
}
