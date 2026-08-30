import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";

import { colors } from "../theme";

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Button({
  title,
  onPress,
  disabled,
  loading,
  variant = "primary",
  style,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "danger" | "ghost" | "success";
  style?: ViewStyle;
}) {
  const bg =
    variant === "danger" ? colors.down : variant === "success" ? colors.up : variant === "ghost" ? colors.card : colors.primary;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{title}</Text>}
    </Pressable>
  );
}

export function Badge({ label, tone = "muted" }: { label: string; tone?: "up" | "down" | "muted" | "warn" }) {
  const color = tone === "up" ? colors.up : tone === "down" ? colors.down : tone === "warn" ? colors.warn : colors.muted;
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[styles.badgeText, { color }]}>{label}</Text>
    </View>
  );
}

export function Row({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLeft}>{left}</Text>
      <Text style={styles.rowRight}>{right}</Text>
    </View>
  );
}

export function ScreenHeader({ title }: { title: string }) {
  return <Text style={styles.header}>{title}</Text>;
}

export function Center({ children }: { children: React.ReactNode }) {
  return <View style={styles.center}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
  },
  button: {
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: {
    color: "#ffffff",
    fontWeight: "600",
    fontSize: 15,
  },
  badge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: "flex-start",
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "600",
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 6,
  },
  rowLeft: {
    color: colors.muted,
    fontSize: 13,
  },
  rowRight: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "600",
    maxWidth: "60%",
  },
  header: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "800",
    marginTop: 16,
    marginBottom: 12,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
});