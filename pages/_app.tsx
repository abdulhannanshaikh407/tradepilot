import React, { useEffect } from "react";
import type { AppProps } from "next/app";
import { useRouter } from "next/router";

import { AuthProvider, useAuth } from "lib/auth";
import { ToastProvider } from "components/ui";
import "styles/globals.css";

class PageErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-bg p-6">
          <div className="max-w-md rounded-2xl border border-red-500/40 bg-bg-card p-6 text-center">
            <h2 className="text-sm font-semibold text-white">Something went wrong rendering this page</h2>
            <p className="mt-2 text-xs text-slate-500">
              A transient error occurred. Reload to continue — your data is safe.
            </p>
            <button
              className="btn-primary mt-4"
              onClick={() => {
                this.setState({ hasError: false });
                if (typeof window !== "undefined") window.location.reload();
              }}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function AuthenticatedApp({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const isDashboard = router.pathname.startsWith("/dashboard");

  if (isDashboard && loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="animate-pulse text-sm text-slate-500">Loading workspace…</div>
      </div>
    );
  }

  return <Component {...pageProps} />;
}

function App(props: AppProps) {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  return (
    <AuthProvider>
      <ToastProvider>
        <PageErrorBoundary>
          <AuthenticatedApp {...props} />
        </PageErrorBoundary>
      </ToastProvider>
    </AuthProvider>
  );
}

export default App;