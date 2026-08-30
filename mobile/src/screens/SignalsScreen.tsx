import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text } from "react-native";

import { api } from "../api";
import { Screen } from "../components/Screen";
import { Badge, Card, Row, ScreenHeader } from "../components/ui";
import { colors, formatDate, formatPrice } from "../theme";
import type { Signal } from "../types";

export function SignalsScreen() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setSignals(await api.signals());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Screen refreshing={signals.length === 0} onRefresh={load}>
      <ScreenHeader title="Signals" />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {signals.length === 0 ? <Text style={styles.muted}>No signals yet.</Text> : null}
      {signals.map((s) => (
        <Card key={s.id} style={styles.cardGap}>
          <Row
            left={s.symbol}
            right={<Badge label={s.direction} tone={s.direction === "LONG" ? "up" : "down"} />}
          />
          <Row left="Entry" right={formatPrice(s.entry_price)} />
          <Row left="Stop loss" right={formatPrice(s.stop_loss)} />
          <Row left="Take profit" right={formatPrice(s.take_profit)} />
          <Row
            left="Risk / reward"
            right={typeof s.risk_reward === "number" ? s.risk_reward.toFixed(2) : "—"}
          />
          {s.confidence ? <Row left="Confidence" right={`${s.confidence.toFixed(1)}%`} /> : null}
          {s.source ? <Row left="Source" right={s.source} /> : null}
          {s.created_at ? <Row left="At" right={formatDate(s.created_at)} /> : null}
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  cardGap: { marginBottom: 12 },
  error: { color: colors.down, marginBottom: 10 },
  muted: { color: colors.muted },
});