import { useCallback, useRef, useState } from "react";
import { api, getToken } from "./api";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export function usePushNotifications() {
  const [supported, setSupported] = useState(
    typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window
  );
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "denied"
  );
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);
  const regRef = useRef<ServiceWorkerRegistration | null>(null);

  const getRegistration = useCallback(async (): Promise<ServiceWorkerRegistration | null> => {
    if (regRef.current) return regRef.current;
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      regRef.current = reg;
      return reg;
    } catch (e) {
      console.error("SW registration failed:", e);
      return null;
    }
  }, []);

  const checkSubscription = useCallback(async () => {
    const reg = await getRegistration();
    if (!reg) return false;
    const subscription = await reg.pushManager.getSubscription();
    const isSubscribed = subscription !== null;
    setSubscribed(isSubscribed);
    return isSubscribed;
  }, [getRegistration]);

  const subscribe = useCallback(async (vapidPublicKey: string): Promise<boolean> => {
    setLoading(true);
    try {
      // Request permission
      if ("Notification" in window) {
        const result = await Notification.requestPermission();
        setPermission(result);
        if (result !== "granted") {
          setLoading(false);
          return false;
        }
      }

      const reg = await getRegistration();
      if (!reg) {
        setLoading(false);
        return false;
      }

      // Check existing subscription
      let subscription = await reg.pushManager.getSubscription();

      // Create new subscription if none exists
      if (!subscription) {
        const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);
        subscription = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        });
      }

      // Send subscription to backend
      const subJson = subscription.toJSON();
      await api("/devices/register", {
        method: "POST",
        body: {
          token: JSON.stringify({
            endpoint: subJson.endpoint,
            keys: subJson.keys,
          }),
          platform: "web",
        },
      });

      setSubscribed(true);
      setLoading(false);
      return true;
    } catch (e) {
      console.error("Push subscribe failed:", e);
      setLoading(false);
      return false;
    }
  }, [getRegistration]);

  const unsubscribe = useCallback(async () => {
    setLoading(true);
    try {
      const reg = await getRegistration();
      if (!reg) {
        setLoading(false);
        return;
      }
      const subscription = await reg.pushManager.getSubscription();
      if (subscription) {
        await subscription.unsubscribe();
        // Notify backend
        const endpoint = subscription.endpoint;
        if (endpoint) {
          api(`/push/unsubscribe?endpoint=${encodeURIComponent(endpoint)}`, {
            method: "DELETE",
          }).catch(() => {});
        }
      }
      setSubscribed(false);
    } finally {
      setLoading(false);
    }
  }, [getRegistration]);

  return {
    supported,
    permission,
    subscribed,
    loading,
    subscribe,
    unsubscribe,
    checkSubscription,
  };
}
