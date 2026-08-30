import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

import { api } from "../api";
import { confirm } from "../components/Screen";
import { Screen } from "../components/Screen";
import { Badge, Button, Card, Row, ScreenHeader } from "../components/ui";
import { colors, formatDate, formatMoney, formatPct, formatPrice } from "../theme";
import type { AutoTradeConfig, AutoTradeStatus, Position } from "../types";

export function AutoTradeScreen() {
  const [status, setStatus] = useState<AutoTradeStatus | null>(null);
  const [configs, setConfigs] = useState<AutoTradeConfig[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState("");
  const [toggling, setToggling] = useState<number | null>(null);
  const [closing, setClosing] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [s, c, p] = await Promise.all([api.autotradeStatus(), api.autotradeConfigs(), api.positions()]);
      setStatus(s);
      setConfigs(c);
      setPositions(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (cfg: AutoTradeConfig) => {
    setToggling(cfg.strategy_id);
    try {
      await api.autotradeUpdateConfig(cfg.strategy_id, { enabled: !cfg.enabled });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setToggling(null);
    }
  };

  const runNow = async () => {
    try {
      await api.runNow();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const close = (pos: Position) => {
    confirm("Close position", `Close ${pos.symbol} ${pos.direction}?`, async () => {
      setClosing(pos.id);
      try {
        await api.closePosition(pos.id);
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setClosing(null);
      }
    });
  };

  const positionTone = (p: Position) => {
    if (p.status === "CLOSED") return "muted";
    const pnl = p.unrealized_pnl ?? p.realized_pnl ?? 0;
    return pnl >= 0 ? "up" : "down";
  };

  return (
    <Screen refreshing={!status} onRefresh={load}>
      <ScreenHeader title="Auto-trade" />

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {status ? (
        <Card style={styles.cardGap}>
          <Row left="Engine" right={status.enabled ? "Running" : "Stopped"} />
          <Row
            left="Data feed"
            right={
              <View style={styles.rowRight}>
                <Text style={styles.rowRightText}>{status.provider === "binance" ? "Binance live" : "Simulated"}</Text>
                <Badge label={status.provider === "binance" ? "Live" : "Demo"} tone={status.provider === "binance" ? "warn" : "muted"} />
              </View>
            }
          />
          <Row left="Scan interval" right={`${status.interval_seconds}s`} />
          <Row left="Strategies watched" right={String(status.strategies_watched)} />
          <Row left="Open positions" right={String(status.open_positions)} />
          <Row left="Last scan" right={formatDate(status.last_run_at)} />
          {status.last_error ? <Row left="Last error" right={status.last_error} /> : null}
        </Card>
      ) : null}

      <Button title="Scan now" onPress={runNow} style={styles.cardGap} />

      <ScreenHeader title="Strategies monitored" />
      {configs.length === 0 ? <Text style={styles.muted}>No strategies being monitored yet.</Text> : null}
      {configs.map((cfg) => (
        <Card key={cfg.id} style={styles.cardGap}>
          <Row
            left={cfg.strategy_name}
            right={
              <View style={styles.switchRow}>
                <Text style={styles.modeText}>{cfg.mode === "live" ? "LIVE" : "paper"}</Text>
                <Switch
                  value={cfg.enabled}
                  onValueChange={() => toggle(cfg)}
                  disabled={toggling === cfg.strategy_id}
                  trackColor={{ true: colors.up, false: colors.border }}
                  thumbColor={cfg.enabled ? "#fff" : colors.muted}
                />
              </View>
            }
          />
          <Row left="Symbol" right={cfg.strategy_symbol} />
          <Row left="Capital" right={formatMoney(cfg.capital)} />
          <Row left="Risk per trade" right={`${cfg.risk_percent}%`} />
          <Row left="Max concurrent" right={String(cfg.max_concurrent)} />
          <Row left="Cooldown" right={cfg.cooldown_minutes > 0 ? `${cfg.cooldown_minutes}m` : "none"} />
          {cfg.last_error ? <Text style={styles.error}>{cfg.last_error}</Text> : null}
        </Card>
      ))}

      <ScreenHeader title="Positions" />
      {positions.length === 0 ? <Text style={styles.muted}>No positions yet.</Text> : null}
      {positions
        .slice()
        .reverse()
        .map((pos) => (
          <Card key={pos.id} style={styles.cardGap}>
            <Row
              left={pos.symbol}
              right={<Badge label={pos.status} tone={positionTone(pos)} />}
            />
            <Row left="Side" right={pos.direction} />
            <Row left="Entry" right={formatPrice(pos.entry_price)} />
            <Row left="Current" right={formatPrice(pos.current_price)} />
            <Row left="Stop loss" right={formatPrice(pos.stop_loss)} />
            <Row left="Take profit" right={formatPrice(pos.take_profit)} />
            <Row
              left="P&L"
              right={`${formatMoney(pos.unrealized_pnl ?? pos.realized_pnl)} (${formatPct(pos.pnl_percent)})`}
            />
            {pos.status === "CLOSED" && pos.exit_reason ? <Row left="Closed via" right={pos.exit_reason} /> : null}
            {pos.status === "OPEN" ? (
              <Button title="Close now" onPress={() => close(pos)} loading={closing === pos.id} variant="danger" style={styles.smallBtn} />
            ) : null}
          </Card>
        ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  cardGap: { marginBottom: 12 },
  smallBtn: { marginTop: 10, paddingVertical: 10 },
  error: { color: colors.down, marginBottom: 10 },
  muted: { color: colors.muted },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  modeText: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  rowRight: { flexDirection: "row", alignItems: "center", gap: 6 },
  rowRightText: { color: colors.text, fontSize: 13, fontWeight: "600" },
});