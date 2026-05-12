/**
 * app/(tabs)/about.tsx — About tab.
 *
 * Per UI spec §7: minimal, single-screen, no scrolling needed.
 */
import React from "react";
import { Linking, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Body, DisplayHL, Meta, SectionLabel } from "../../components/ui";
import { fonts, space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { Pressable, Text } from "react-native";

function Link({ label, url }: { label: string; url: string }) {
  const { palette } = useTheme();
  return (
    <Pressable
      onPress={() => Linking.openURL(url)}
      style={({ pressed }) => [
        { paddingVertical: space.sm, opacity: pressed ? 0.6 : 1 },
      ]}
    >
      <Text style={{ fontFamily: fonts.sans, fontSize: 14, color: palette.accent }}>
        {label} →
      </Text>
    </Pressable>
  );
}

export default function AboutTab() {
  const { palette } = useTheme();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <View
        style={{
          flex: 1,
          padding: space.xxxl,
          justifyContent: "center",
          gap: space.lg,
        }}
      >
        <DisplayHL style={{ color: palette.accent }}>Brevio</DisplayHL>

        <Text
          style={{
            fontFamily: fonts.serif,
            fontStyle:  "italic",
            fontSize:   18,
            color:      palette.textPrimary,
            lineHeight: 26,
          }}
        >
          One story, every source, full timeline.
        </Text>

        <Body style={{ marginTop: space.md }}>
          Brevio is a daily news digest for AI, technology, business, and science. We
          dedupe coverage across dozens of sources so you can see each story once,
          with every angle.
        </Body>

        <View style={{ marginTop: space.xl }}>
          <SectionLabel muted>BUILT BY</SectionLabel>
          <Meta style={{ marginTop: space.xs }}>Cristian Samson</Meta>
        </View>

        <View style={{ marginTop: space.md }}>
          <Link label="Send feedback" url="mailto:samsoncristian@gmail.com" />
          <Link label="View on GitHub" url="https://github.com/CrSamson/brevio-ai" />
        </View>
      </View>
    </SafeAreaView>
  );
}
