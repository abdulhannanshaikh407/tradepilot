import React, { useCallback, useEffect, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api } from "../api";
import { Screen } from "../components/Screen";
import { Button, Card, Row, ScreenHeader } from "../components/ui";
import { colors } from "../theme";
import type { BrokerAccount, BrokerConnection } from "../types";

const BROKERS = [
  { key: "alpaca", label: "Alpaca (Stocks)", accountTypes: ["paper", "live"] },
  { key: "binance", label: "Binance (Crypto)", accountTypes: ["live"] },
];

export function BrokerSettingsScreen() {
  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [selectedBroker, setSelectedBroker] = useState("alpaca");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountType, setAccountType] = useState("paper");
  const [loading, setLoading] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<BrokerAccount | null>(null);
  const [selectedConnId, setSelectedConnId] = useState<number | null>(null);

  const loadConnections = useCallback(async () => {
    try {
      const result = await api.getConnectedBrokers();
      setConnections(result);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const handleConnect = async () => {
    if (!apiKey || !apiSecret) {
      Alert.alert("Error", "API key and secret are required.");
      return;
    }

    const brokerConfig = BROKERS.find((b) => b.key === selectedBroker);
    if (brokerConfig && !brokerConfig.accountTypes.includes(accountType)) {
      Alert.alert("Error", `${brokerConfig.label} only supports ${brokerConfig.accountTypes.join(" or ")} accounts.`);
      return;
    }

    if (accountType === "live") {
      Alert.alert(
        "Live Trading",
        "You are connecting a LIVE broker account. Real money will be used. Continue?",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Yes, Continue", onPress: doConnect },
        ]
      );
    } else {
      doConnect();
    }
  };

  const doConnect = async () => {
    setLoading(true);
    try {
      await api.connectBroker({
        broker: selectedBroker,
        api_key: apiKey,
        api_secret: apiSecret,
        account_type: accountType,
      });
      Alert.alert("Success", `Connected to ${selectedBroker.toUpperCase()}`);
      setApiKey("");
      setApiSecret("");
      loadConnections();
    } catch (e: any) {
      Alert.alert("Error", e.message || "Connection failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async (connId: number) => {
    Alert.alert("Disconnect", "Remove this broker connection?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Disconnect",
        style: "destructive",
        onPress: async () => {
          try {
            await api.disconnectBroker(connId);
            loadConnections();
            if (selectedConnId === connId) {
              setSelectedAccount(null);
              setSelectedConnId(null);
            }
          } catch (e: any) {
            Alert.alert("Error", e.message);
          }
        },
      },
    ]);
  };

  const viewAccount = async (connId: number) => {
    try {
      const account = await api.getBrokerAccount(connId);
      setSelectedAccount(account);
      setSelectedConnId(connId);
    } catch (e: any) {
      Alert.alert("Error", e.message || "Failed to fetch account.");
    }
  };

  return (
    <Screen>
      <ScrollView style={styles.container}>
        <ScreenHeader title="Broker Settings" />

        {/* Connect Form */}
        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>Connect Broker</Text>

          <Text style={styles.label}>Broker</Text>
          <View style={styles.brokerRow}>
            {BROKERS.map((b) => (
              <Button
                key={b.key}
                title={b.label}
                onPress={() => {
                  setSelectedBroker(b.key);
                  setAccountType(b.accountTypes[0]);
                }}
                variant={selectedBroker === b.key ? "primary" : "secondary"}
              />
            ))}
          </View>

          <Text style={styles.label}>Account Type</Text>
          <View style={styles.brokerRow}>
            {BROKERS.find((b) => b.key === selectedBroker)?.accountTypes.map((t) => (
              <Button
                key={t}
                title={t.charAt(0).toUpperCase() + t.slice(1)}
                onPress={() => setAccountType(t)}
                variant={accountType === t ? "primary" : "secondary"}
              />
            ))}
          </View>

          {accountType === "live" && (
            <View style={styles.warning}>
              <Text style={styles.warningText}>
                LIVE TRADING ENABLED{"\n"}Real money will be used. Only continue if you understand the risks.
              </Text>
            </View>
          )}

          <TextInput
            style={styles.input}
            placeholder="API Key"
            value={apiKey}
            onChangeText={setApiKey}
            secureTextEntry
            autoCapitalize="none"
          />
          <TextInput
            style={styles.input}
            placeholder="API Secret"
            value={apiSecret}
            onChangeText={setApiSecret}
            secureTextEntry
            autoCapitalize="none"
          />

          <Button
            title={loading ? "Connecting..." : `Connect ${selectedBroker.toUpperCase()}`}
            onPress={handleConnect}
          />
        </Card>

        {/* Connected Brokers */}
        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>Connected Brokers</Text>
          {connections.length === 0 ? (
            <Text style={styles.emptyText}>No brokers connected yet.</Text>
          ) : (
            connections.map((c) => (
              <View key={c.id} style={styles.connRow}>
                <View style={styles.connInfo}>
                  <Text style={styles.connBroker}>
                    {c.broker.toUpperCase()} - {c.account_type}
                  </Text>
                  <Text style={styles.connStatus}>
                    {c.is_verified ? "Verified" : "Pending"}
                  </Text>
                </View>
                <View style={styles.connActions}>
                  <Button title="View" onPress={() => viewAccount(c.id)} variant="secondary" />
                  <Button title="Disconnect" onPress={() => handleDisconnect(c.id)} variant="danger" />
                </View>
              </View>
            ))
          )}
        </Card>

        {/* Account Details */}
        {selectedAccount && (
          <Card style={styles.card}>
            <Text style={styles.sectionTitle}>Account Details</Text>
            <Row left="Balance" right={`$${selectedAccount.balance.toFixed(2)}`} />
            <Row left="Buying Power" right={`$${selectedAccount.buying_power.toFixed(2)}`} />
            <Row left="Cash" right={`$${selectedAccount.cash.toFixed(2)}`} />
            <Row left="Daily P&L" right={`$${selectedAccount.daily_pnl.toFixed(2)}`} />
            <Row left="Broker" right={selectedAccount.broker_name} />
            <Row left="Type" right={selectedAccount.account_type} />

            {selectedAccount.positions.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: 12 }]}>Open Positions</Text>
                {selectedAccount.positions.map((p, i) => (
                  <View key={i} style={styles.posRow}>
                    <Text style={styles.posSymbol}>{p.symbol}</Text>
                    <Text style={styles.posQty}>x{p.quantity.toFixed(4)}</Text>
                    <Text style={p.pnl >= 0 ? styles.posPnlUp : styles.posPnlDown}>
                      ${p.pnl.toFixed(2)} ({p.pnl_percent.toFixed(2)}%)
                    </Text>
                  </View>
                ))}
              </>
            )}
          </Card>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  card: { marginBottom: 12 },
  sectionTitle: { fontSize: 16, fontWeight: "bold", color: colors.text, marginBottom: 10 },
  label: { color: colors.muted, fontSize: 12, marginTop: 8, marginBottom: 4 },
  brokerRow: { flexDirection: "row", gap: 8, marginBottom: 8 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 12,
    color: colors.text,
    backgroundColor: colors.card,
    marginBottom: 8,
  },
  warning: {
    backgroundColor: "rgba(255, 193, 7, 0.15)",
    padding: 10,
    borderRadius: 8,
    marginBottom: 8,
  },
  warningText: { color: "#ffc107", fontSize: 12 },
  emptyText: { color: colors.muted, fontSize: 13, textAlign: "center", padding: 20 },
  connRow: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  connInfo: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  connBroker: { color: colors.text, fontWeight: "bold" },
  connStatus: { color: colors.accent, fontSize: 12 },
  connActions: { flexDirection: "row", gap: 8 },
  posRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  posSymbol: { color: colors.text, fontWeight: "bold" },
  posQty: { color: colors.muted },
  posPnlUp: { color: "#22c55e" },
  posPnlDown: { color: "#ef4444" },
});
