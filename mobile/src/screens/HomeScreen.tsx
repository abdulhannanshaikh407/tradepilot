import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { api } from "../api";
import { Screen } from "../components/Screen";
import { Badge, Card, Row, ScreenHeader } from "../components/ui";
import { colors, formatMoney, formatPct, formatPrice } from "../theme";
import type { DashboardStats } from "../types";

export function HomeScreen() {
  const [data, setData] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await api.dashboard());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Screen refreshing={!data} onRefresh={load}>
      <ScreenHeader title="Portfolio" />
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {data ? (
        <>
          <View style={styles.statRow}>
            <Card style={styles.statCard}>
              <Text style={styles.statLabel}>Value</Text>
              <Text style={styles.statValue}>{formatMoney(data.portfolio_value)}</Text>
            </Card>
            <Card style={styles.statCard}>
              <Text style={styles.statLabel}>Net P&L</Text>
              <Text style={[styles.statValue, { color: (data.net_pnl ?? 0) >= 0 ? colors.up : colors.down }]}>
                {formatMoney(data.net_pnl)}
              </Text>
            </Card>
          </View>
          <View style={styles.statRow}>
            <Card style={styles.statCard}>
              <Text style={styles.statLabel}>Win rate</Text>
              <Text style={styles.statValue}>{formatPct(data.win_rate)}</Text>
            </Card>
            <Card style={styles.statCard}>
              <Text style={styles.statLabel}>Max drawdown</Text>
              <Text style={[styles.statValue, { color: colors.down }]}>{formatPct(data.max_drawdown)}</Text>
            </Card>
          </View>

          {data.recent_signals.length > 0 ? (
            <>
              <ScreenHeader title="Latest signals" />
              {data.recent_signals.map((s) => (
                <Card key={s.id} style={styles.signalCard}>
                  <Row left={s.symbol} right={<Badge label={s.direction} tone={s.direction === "LONG" ? "up" : "down"} />} />
                  <Row left="Entry" right={formatPrice(s.entry_price)} />
                  <Row left="Confidence" right={s.confidence ? `${s.confidence.toFixed(1)}%` : "—"} />
                </Card>
              ))}
            </>
          ) : null}

          {data.recent_activity.length > 0 ? (
            <>
              <ScreenHeader title="Recent activity" />
              <Card>
                {data.recent_activity.map((a, i) => (
                  <Text key={i} style={[styles.activity, i > 0 && styles.activityBorder]}>
                    {a.title}
                  </Text>
                ))}
              </Card>
            </>
          ) : null}
        </>
      ) : (
        <Text style={styles.muted}>Loading dashboard…</Text>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  statRow: { flexDirection: "row", gap: 12 },
  statCard: { flex: 1 },
  statLabel: { color: colors.muted, fontSize: 12, marginBottom: 4 },
  statValue: { color: colors.text, fontSize: 18, fontWeight: "800" },
  signalCard: { marginBottom: 10 },
  activity: { color: colors.text, fontSize: 13, paddingVertical: 8 },
  activityBorder: { borderTopWidth: 1, borderTopColor: colors.border },
  error: { color: colors.down, marginBottom: 10 },
  muted: { color: colors.muted },
});