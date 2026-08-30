import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";

import { api, setToken } from "../api";
import { Button, Center } from "../components/ui";
import { Field, errorMessage } from "../components/Screen";
import { colors } from "../theme";
import type { User } from "../types";

export function LoginScreen({ onAuthed }: { onAuthed: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<"login" | "demo" | null>(null);
  const [error, setError] = useState("");

  const doLogin = async () => {
    if (!email || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy("login");
    setError("");
    try {
      const res = await api.login(email.trim(), password);
      await setToken(res.access_token);
      onAuthed(res.user);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const doDemo = async () => {
    setBusy("demo");
    setError("");
    try {
      const res = await api.demo();
      await setToken(res.access_token);
      onAuthed(res.user);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const doSignup = async () => {
    if (!email || !password) {
      setError("Enter an email and password to create an account.");
      return;
    }
    setBusy("login");
    setError("");
    try {
      const name = email.split("@")[0];
      const res = await api.signup(email.trim(), password, name);
      await setToken(res.access_token);
      onAuthed(res.user);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Center>
        <View style={styles.box}>
          <Text style={styles.logo}>📊 TradePilot AI</Text>
          <Text style={styles.tagline}>
            AI signals • TradingView alerts • auto-execution
          </Text>

          <Field label="Email" value={email} onChangeText={setEmail} placeholder="you@example.com" keyboardType="email-address" autoCapitalize="none" />
          <Field label="Password" value={password} onChangeText={setPassword} placeholder="••••••••" secure autoCapitalize="none" />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Button title="Log in" onPress={doLogin} loading={busy === "login"} />
          <View style={styles.gap} />
          <Button title="Create account" onPress={doSignup} disabled={busy !== null} variant="ghost" />
          <View style={styles.gap} />
          <Button title="Try the demo account" onPress={doDemo} loading={busy === "demo"} variant="success" />
        </View>
      </Center>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  box: { width: "88%", maxWidth: 420 },
  logo: { color: colors.text, fontSize: 26, fontWeight: "800", textAlign: "center" },
  tagline: { color: colors.muted, fontSize: 13, textAlign: "center", marginBottom: 24, marginTop: 4 },
  gap: { height: 10 },
  error: { color: colors.down, fontSize: 13, marginBottom: 12, textAlign: "center" },
});