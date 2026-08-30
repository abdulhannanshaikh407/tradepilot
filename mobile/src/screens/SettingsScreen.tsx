import { useNavigation } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text } from "react-native";

import { api, baseUrl, setToken } from "../api";
import { Screen } from "../components/Screen";
import { Button, Card, Row, ScreenHeader } from "../components/ui";
import { colors } from "../theme";

export function SettingsScreen() {
  const navigation = useNavigation();
  const [me, setMe] = useState<{ email: string; name: string; plan: string; is_demo: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      /* handled by logout path */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const logout = async () => {
    await setToken(null);
    navigation.reset({ index: 0, routes: [{ name: "Login" as never }] });
  };

  return (
    <Screen>
      <ScreenHeader title="Settings" />
      {me ? (
        <Card style={styles.cardGap}>
          <Row left="Name" right={me.name} />
          <Row left="Email" right={me.email} />
          <Row left="Plan" right={me.plan} />
          <Row left="Account" right={me.is_demo ? "demo" : "personal"} />
        </Card>
      ) : null}
      <Card style={styles.cardGap}>
        <Row left="API server" right={baseUrl()} />
        <Text style={styles.hint}>
          Point the app at your deployed backend by setting EXPO_PUBLIC_API_URL before building the app.
        </Text>
      </Card>
      <Button title="Log out" onPress={logout} variant="danger" />
    </Screen>
  );
}

const styles = StyleSheet.create({
  cardGap: { marginBottom: 12 },
  hint: { color: colors.muted, fontSize: 12, marginTop: 10 },
});