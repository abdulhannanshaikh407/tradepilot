import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { api } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function registerForPushNotifications(): Promise<string | null> {
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== "granted") {
      console.log("Push notification permission not granted");
      return null;
    }

    const tokenData = await Notifications.getExpoPushTokenAsync();
    const pushToken = tokenData.data;

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("tradepilot_alerts", {
        name: "TradePilot Alerts",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#2563EB",
        sound: "default",
      });
    }

    return pushToken;
  } catch (error) {
    console.error("Failed to register for push notifications:", error);
    return null;
  }
}

export async function registerDeviceToken(
  pushToken: string,
  platform: "android" | "ios" | "web"
): Promise<boolean> {
  try {
    const result = await api.registerDevice({ token: pushToken, platform });
    return !!result.id;
  } catch (error) {
    console.error("Failed to register device token:", error);
    return false;
  }
}

export function setupNotificationListeners(
  onNotificationReceived: (notification: Notifications.Notification) => void,
  onNotificationTapped: (response: Notifications.NotificationResponse) => void
) {
  const receivedSub = Notifications.addNotificationReceivedListener(
    onNotificationReceived
  );

  const responseSub = Notifications.addNotificationResponseReceivedListener(
    onNotificationTapped
  );

  return () => {
    receivedSub.remove();
    responseSub.remove();
  };
}
