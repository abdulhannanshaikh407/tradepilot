import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import Head from "next/head";
import { BarChart3, FlaskConical } from "lucide-react";

import { useAuth } from "lib/auth";
import { ApiError } from "lib/api";
import { Button } from "components/ui";

export default function Signup() {
  const router = useRouter();
  const { signup, demo, user } = useAuth();
  const [name, setName] = useState("");
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
      await signup(name, email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Signup failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const enterDemo = async () => {
    try {
      await demo();
      router.push("/dashboard");
    } catch {
      setError("Could not enter the demo workspace.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <Head>
        <title>Create account — TradePilot AI</title>
      </Head>
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15">
            <BarChart3 className="h-5 w-5 text-emerald-400" />
          </div>
          <span className="text-base font-bold text-white">TradePilot AI</span>
        </Link>

        <div className="card p-6">
          <h1 className="text-lg font-bold text-white">Create your account</h1>
          <p className="mt-1 text-xs text-slate-500">Free plan includes 3 AI analyses.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label">Name</label>
              <input
                className="input"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Kai Trader"
              />
            </div>
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
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            {error && (
              <div className="rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-red-300">
                {error}
              </div>
            )}
            <Button type="submit" loading={submitting} className="w-full">
              Create account
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-[11px] text-slate-600">
            <div className="h-px flex-1 bg-line" /> or <div className="h-px flex-1 bg-line" />
          </div>

          <Button variant="secondary" className="w-full" onClick={enterDemo}>
            <FlaskConical className="h-4 w-4" /> Explore Demo — no signup
          </Button>
        </div>

        <p className="mt-5 text-center text-xs text-slate-500">
          Already registered?{" "}
          <Link href="/login" className="font-medium text-emerald-400 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}