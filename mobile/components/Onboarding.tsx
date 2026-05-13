/**
 * components/Onboarding.tsx — first-launch welcome overlay.
 *
 * UI spec §8: single-screen welcome with logotype, tagline, three short
 * value bullets, and a "Start reading" peach pill. Dismissed once, then
 * skipped on every subsequent launch via AsyncStorage flag.
 *
 * Mounted at the root level (above the tab Stack) so the user sees it
 * before any data UI on first launch.
 */
import React, { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View, useColorScheme } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { Body, DisplayHL, Meta, SectionLabel } from "./ui";
import { fonts, palette as paletteFor, radius, space } from "../lib/theme";

const STORAGE_KEY = "brevio.seen_onboarding.v1";

const BULLETS = [
  {
    label:  "ONE STORY",
    detail: "We dedupe coverage across dozens of sources so you see each event once.",
  },
  {
    label:  "EVERY SOURCE",
    detail: "Every angle from every outlet, grouped into one story card.",
  },
  {
    label:  "FULL TIMELINE",
    detail: "See who reported what, and when — oldest first.",
  },
];

type Props = {
  /** Render this once the user has dismissed onboarding (or has seen it before). */
  children: React.ReactNode;
};

export function OnboardingGate({ children }: Props) {
  const sysScheme = useColorScheme();
  const scheme = sysScheme === "dark" ? "dark" : "light";
  const palette = paletteFor(scheme);

  // null = checking; true = needs onboarding; false = done.
  const [needsOnboarding, setNeedsOnboarding] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((v) => {
        if (!cancelled) setNeedsOnboarding(v !== "1");
      })
      .catch(() => {
        // AsyncStorage hiccup → show onboarding rather than blocking forever.
        if (!cancelled) setNeedsOnboarding(true);
      });
    return () => { cancelled = true; };
  }, []);

  const dismiss = async () => {
    setNeedsOnboarding(false);
    try {
      await AsyncStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // Non-fatal — they'll see onboarding once more next launch.
    }
  };

  // While we're checking, render children underneath. This avoids a black
  // flash; if onboarding is needed it'll just pop on top a moment later.
  if (needsOnboarding !== true) return <>{children}</>;

  return (
    <View style={[styles.root, { backgroundColor: palette.bg }]}>
      <View style={styles.content}>
        <DisplayHL style={{ color: palette.accent, fontSize: 44, lineHeight: 50 }}>
          Brevio
        </DisplayHL>

        <Text
          style={{
            fontFamily: fonts.serif,
            fontStyle:  "italic",
            fontSize:   20,
            lineHeight: 28,
            color:      palette.textPrimary,
            marginTop:  space.md,
          }}
        >
          One story, every source, full timeline.
        </Text>

        <View style={{ marginTop: space.xxxl, gap: space.xl }}>
          {BULLETS.map((b) => (
            <View key={b.label}>
              <SectionLabel style={{ color: palette.accent }}>{b.label}</SectionLabel>
              <Body style={{ marginTop: space.xs }}>{b.detail}</Body>
            </View>
          ))}
        </View>
      </View>

      <Pressable
        onPress={dismiss}
        accessibilityRole="button"
        accessibilityLabel="Start reading"
        style={({ pressed }) => [
          styles.button,
          {
            backgroundColor: palette.accent,
            opacity:         pressed ? 0.85 : 1,
          },
        ]}
      >
        <Meta style={{ color: palette.accentText, fontFamily: fonts.sansSemibold, fontSize: 14, letterSpacing: 0.5 }}>
          START READING
        </Meta>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    position: "absolute",
    top: 0, left: 0, right: 0, bottom: 0,
    paddingHorizontal: space.xxxl,
    paddingTop:        space.xxxl * 2,
    paddingBottom:     space.xxxl,
    justifyContent:    "space-between",
    zIndex:            1000,
  },
  content: {
    flexShrink: 1,
  },
  button: {
    alignSelf:        "stretch",
    alignItems:       "center",
    justifyContent:   "center",
    paddingVertical:   space.lg,
    borderRadius:      radius.chip,
  },
});
