/**
 * app/(tabs)/about.tsx — About tab.
 *
 * UI spec §7: minimal, single-screen, no scrolling needed. Centered
 * logotype + italic-serif tagline + short description, then a small
 * stack of links (feedback / source / privacy), and a footer with
 * "Built by Cristian Samson" + app version pulled from app.json.
 */
import React from "react";
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Constants from "expo-constants";
import { Ionicons } from "@expo/vector-icons";

import { Body, DisplayHL, Meta, SectionLabel } from "../../components/ui";
import { fonts, space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

function LinkRow({ icon, label, url }: { icon: IconName; label: string; url: string }) {
  const { palette } = useTheme();
  return (
    <Pressable
      onPress={() => Linking.openURL(url).catch(() => undefined)}
      accessibilityRole="link"
      accessibilityLabel={label}
      style={({ pressed }) => [
        {
          flexDirection:    "row",
          alignItems:       "center",
          paddingVertical:   space.md,
          opacity:           pressed ? 0.6 : 1,
        },
      ]}
    >
      <Ionicons name={icon} size={18} color={palette.accent} style={{ marginRight: space.md }} />
      <Text style={{ flex: 1, fontFamily: fonts.sansMedium, fontSize: 15, color: palette.textPrimary }}>
        {label}
      </Text>
      <Ionicons name="chevron-forward" size={16} color={palette.textMuted} />
    </Pressable>
  );
}

export default function AboutTab() {
  const { palette } = useTheme();
  const version = (Constants.expoConfig?.version as string | undefined) ?? "0.1.0";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{
          flexGrow:        1,
          paddingHorizontal: space.xxxl,
          paddingTop:       space.xxxl,
          paddingBottom:    space.xxxl,
        }}
      >
        <View style={{ alignItems: "center", marginTop: space.xl }}>
          <DisplayHL style={{ color: palette.accent, fontSize: 44, lineHeight: 50, textAlign: "center" }}>
            Brevio
          </DisplayHL>
          <Text
            style={{
              fontFamily: fonts.serif,
              fontStyle:  "italic",
              fontSize:   18,
              lineHeight: 26,
              color:      palette.textPrimary,
              marginTop:  space.md,
              textAlign:  "center",
            }}
          >
            One story, every source, full timeline.
          </Text>
        </View>

        <Body style={{ marginTop: space.xxxl, textAlign: "center", paddingHorizontal: space.md }}>
          A daily news digest for AI, technology, business, and science.
          We dedupe coverage across dozens of sources so you can see each
          story once, with every angle.
        </Body>

        <View style={{ marginTop: space.xxxl }}>
          <SectionLabel muted style={{ marginBottom: space.sm }}>LINKS</SectionLabel>
          <View style={{ borderTopWidth: 1, borderTopColor: palette.border }} />
          <LinkRow
            icon="mail-outline"
            label="Send feedback"
            url="mailto:samsoncristian@gmail.com?subject=Brevio%20feedback"
          />
          <View style={{ borderTopWidth: 1, borderTopColor: palette.border }} />
          <LinkRow
            icon="logo-github"
            label="View source on GitHub"
            url="https://github.com/CrSamson/brevio-ai"
          />
          <View style={{ borderTopWidth: 1, borderTopColor: palette.border }} />
        </View>

        <View style={{ flex: 1 }} />

        <View style={{ alignItems: "center", marginTop: space.xxxl }}>
          <Meta muted>Built by Cristian Samson</Meta>
          <Meta muted style={{ marginTop: space.xs }}>v{version}</Meta>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
