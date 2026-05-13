/**
 * app/browser.tsx — in-app WebView modal.
 *
 * UI spec §6.4: slides up from the bottom (registered with
 * `presentation: "modal"` in _layout.tsx), shows a top bar with hostname +
 * close, a thin peach progress bar driven by onLoadProgress, and renders the
 * article URL in a react-native-webview.
 *
 * Web behaviour: react-native-webview-for-web doesn't have full feature
 * parity. We fall back to Linking.openURL on web so PWA users get the
 * article in a new tab instead of a broken iframe (many news sites
 * X-Frame-Options: DENY which would render blank).
 */
import React, { useEffect, useState } from "react";
import { Linking, Platform, Pressable, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";

import { Body, Meta } from "../components/ui";
import { space } from "../lib/theme";
import { useTheme } from "../lib/useTheme";

let WebView: any = null;
try {
  // Dynamic require so the web bundle doesn't choke if the native module
  // isn't installed on this platform.
  WebView = require("react-native-webview").WebView;
} catch {
  WebView = null;
}

function hostnameOf(raw: string | undefined): string {
  if (!raw) return "";
  try {
    return new URL(raw).hostname.replace(/^www\./, "");
  } catch {
    return raw;
  }
}

export default function InAppBrowser() {
  const { palette } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ url: string; source?: string }>();

  const targetUrl = typeof params.url === "string" ? params.url : "";
  const sourceLabel = typeof params.source === "string" ? params.source : "";
  const host = hostnameOf(targetUrl);

  const [progress, setProgress] = useState(0);

  // Web fallback: open in a new tab via the system browser and pop the modal.
  useEffect(() => {
    if (Platform.OS === "web" && targetUrl) {
      WebBrowser.openBrowserAsync(targetUrl).catch(() => Linking.openURL(targetUrl));
      router.back();
    }
  }, [targetUrl, router]);

  if (!targetUrl) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }}>
        <View style={{ padding: space.xl }}>
          <Body>No article URL.</Body>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <View style={[styles.header, { borderBottomColor: palette.border }]}>
        <View style={{ flex: 1 }}>
          {sourceLabel ? (
            <Meta numberOfLines={1} style={{ color: palette.accent, fontSize: 11, letterSpacing: 1 }}>
              {sourceLabel.toUpperCase()}
            </Meta>
          ) : null}
          <Body numberOfLines={1} style={{ marginTop: 2 }}>
            {host}
          </Body>
        </View>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Close"
          style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1, padding: space.sm }]}
        >
          <Ionicons name="close" size={24} color={palette.textPrimary} />
        </Pressable>
      </View>

      {/* progress bar */}
      <View style={{ height: 2, backgroundColor: palette.border }}>
        <View
          style={{
            height:          2,
            backgroundColor: palette.accent,
            width:           `${Math.round(progress * 100)}%`,
            opacity:         progress > 0 && progress < 1 ? 1 : 0,
          }}
        />
      </View>

      {WebView ? (
        <WebView
          source={{ uri: targetUrl }}
          style={{ flex: 1, backgroundColor: palette.bg }}
          onLoadProgress={({ nativeEvent }: { nativeEvent: { progress: number } }) =>
            setProgress(nativeEvent.progress)
          }
          onLoadEnd={() => setProgress(1)}
        />
      ) : (
        <View style={{ flex: 1, padding: space.xl, justifyContent: "center" }}>
          <Body muted>Opening in system browser…</Body>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection:    "row",
    alignItems:       "center",
    paddingHorizontal: space.xl,
    paddingVertical:   space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap:               space.md,
  },
});
