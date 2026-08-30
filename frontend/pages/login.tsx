import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import Head from "next/head";
import { BarChart3, FlaskConical } from "lucide-react";

import { useAuth } from "lib/auth";
import { ApiError } from "lib/api";
import { Button } from "components/ui";

export default function Login() {
  const router = useRouter();
  const { login, demo, user, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const enterDemo = async () => {
    setError("");
    setSubmitting(true);
    try {
      await demo();
      router.push("/dashboard");
    } catch {
      setError("Could not enter the demo workspace.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <Head>
        <title>Sign in — TradePilot AI</title>
      </Head>
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15">
            <BarChart3 className="h-5 w-5 text-emerald-400" />
          </div>
          <span className="text-base font-bold text-white">TradePilot AI</span>
        </Link>

        <div className="card p-6">
          <h1 className="text-lg font-bold text-white">Welcome back</h1>
          <p className="mt-1 text-xs text-slate-500">Sign in to your workspace.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label">Email</label>
              <input
                className="input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@email.com"
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div className="rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-red-300">
                {error}
              </div>
            )}
            <Button type="submit" loading={submitting} className="w-full">
              Sign in
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-[11px] text-slate-600">
            <div className="h-px flex-1 bg-line" /> or <div className="h-px flex-1 bg-line" />
          </div>

          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={enterDemo}
            loading={submitting && !email}
          >
            <FlaskConical className="h-4 w-4" /> Enter Demo Workspace
          </Button>
        </div>

        <p className="mt-5 text-center text-xs text-slate-500">
          New here?{" "}
          <Link href="/signup" className="font-medium text-emerald-400 hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}