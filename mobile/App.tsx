import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";

import { api, loadToken, setToken } from "./src/api";
import { colors } from "./src/theme";
import type { User } from "./src/types";
import { AutoTradeScreen } from "./src/screens/AutoTradeScreen";
import { BrokerSettingsScreen } from "./src/screens/BrokerSettingsScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import { SignalsScreen } from "./src/screens/SignalsScreen";
import { StrategiesScreen } from "./src/screens/StrategiesScreen";
import {
  registerForPushNotifications,
  registerDeviceToken,
  setupNotificationListeners,
} from "./src/notifications";

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

const navTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: colors.bg,
    card: colors.card,
    text: colors.text,
    border: colors.border,
    primary: colors.primary,
  },
};

const icons: Record<string, string> = {
  Home: "📊",
  AutoTrade: "🤖",
  Signals: "🔔",
  Strategies: "📈",
  Settings: "⚙️",
};

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerStyle: { backgroundColor: colors.card },
        headerTintColor: colors.text,
        tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 11 },
        tabBarIcon: ({ color }) => <Text style={{ fontSize: 15 }}>{icons[route.name]}</Text>,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="AutoTrade" component={AutoTradeScreen} />
      <Tab.Screen name="Signals" component={SignalsScreen} />
      <Tab.Screen name="Strategies" component={StrategiesScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}

export default function App() {
  const [booted, setBooted] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    (async () => {
      const tok = await loadToken();
      if (tok) {
        try {
          const me = await api.me();
          setUser(me);
        } catch {
          await setToken(null);
        }
      }
      setBooted(true);
    })();
  }, []);

  useEffect(() => {
    if (!user) return;

    const setupPush = async () => {
      const token = await registerForPushNotifications();
      if (token) {
        const platform: "android" | "ios" | "web" =
          require("react-native").Platform.OS === "android" ? "android" : "ios";
        await registerDeviceToken(token, platform);
      }
    };
    setupPush();

    const cleanup = setupNotificationListeners(
      (notification) => {
        console.log("Notification received:", notification.request.content);
      },
      (response) => {
        console.log("Notification tapped:", response.notification.request.content);
      }
    );

    return cleanup;
  }, [user]);

  const onAuthed = useCallback((u: User) => setUser(u), []);

  if (!booted) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style="light" />
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {user ? (
          <Stack.Screen name="Main">
            {() => <MainTabs />}
          </Stack.Screen>
        ) : (
          <Stack.Screen name="Login">
            {() => <LoginScreen onAuthed={onAuthed} />}
          </Stack.Screen>
        )}
        <Stack.Screen
          name="BrokerSettings"
          component={BrokerSettingsScreen}
          options={{ headerShown: true, title: "Broker Settings", headerStyle: { backgroundColor: colors.card }, headerTintColor: colors.text }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}