import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { api } from "../api";
import { Screen } from "../components/Screen";
import { Badge, Card, Row, ScreenHeader } from "../components/ui";
import { colors } from "../theme";
import type { Strategy } from "../types";

export function StrategiesScreen() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setStrategies(await api.strategies());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const directionTone = (d: string) => (d === "LONG" ? "up" : "down") as "up" | "down";

  return (
    <Screen refreshing={strategies.length === 0} onRefresh={load}>
      <ScreenHeader title="Strategies" />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {strategies.length === 0 ? <Text style={styles.muted}>No strategies yet.</Text> : null}
      {strategies.map((s) => (
        <Card key={s.id} style={styles.cardGap}>
          <Row
            left={s.name}
            right={
              <View style={styles.badges}>
                <Badge label={s.direction} tone={directionTone(s.direction)} />
                {s.is_active ? <Badge label="active" tone="up" /> : null}
                {s.is_demo ? <Badge label="demo" /> : null}
              </View>
            }
          />
          <Row left="Asset" right={s.asset} />
          <Row left="Timeframe" right={s.timeframe} />
          <Row
            left="Stop loss"
            right={s.stop_loss_value != null ? `${s.stop_loss_value}${s.stop_loss_type === "percent" ? "%" : ""}` : "—"}
          />
          <Row
            left="Take profit"
            right={s.take_profit_value != null ? `${s.take_profit_value}${s.take_profit_type === "percent" ? "%" : ""}` : "—"}
          />
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  cardGap: { marginBottom: 12 },
  badges: { flexDirection: "row", gap: 6 },
  error: { color: colors.down, marginBottom: 10 },
  muted: { color: colors.muted },
});