/**
 * components/ui/TopicChip.tsx — uppercase topic label.
 *
 * Two visual modes:
 *   - inline:  small uppercase peach text on cream (cards, detail header).
 *              Used as "AI · BUSINESS" labels above headlines (UI spec §3.2).
 *   - filter:  pill shape, active = filled peach; inactive = bordered.
 *              Used for the horizontal filter row on the Topics tab (UI spec §4.1).
 */
import React from "react";
import { Pressable, StyleSheet, View, type PressableProps, type StyleProp, type TextStyle, type ViewStyle } from "react-native";

import { radius, space, text as textTokens } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { Meta } from "./Text";

type Mode = "inline" | "filter";

type Props = {
  label:   string;
  mode?:   Mode;
  active?: boolean;          // only meaningful for mode="filter"
  onPress?: PressableProps["onPress"];
  /**
   * Style override. Accepts ViewStyle (filter pill) OR TextStyle (inline label)
   * since the component renders different DOM in each mode. Loose typing here
   * is acceptable for a design-system primitive — callers usually pass
   * margin/spacing props that work in both contexts.
   */
  style?:  StyleProp<ViewStyle | TextStyle>;
};

export function TopicChip({ label, mode = "inline", active = false, onPress, style }: Props) {
  const { palette } = useTheme();
  const upper = label.toUpperCase();

  if (mode === "inline") {
    return (
      <Meta
        style={[
          {
            ...textTokens.chip,
            color: palette.accent,
            textTransform: "uppercase",
          },
          style as StyleProp<TextStyle>,
        ]}
      >
        {upper}
      </Meta>
    );
  }

  // filter mode — pill
  const pillBg     = active ? palette.accent : palette.cardBg;
  const pillBorder = active ? palette.accent : palette.accent + "55";
  const labelColor = active ? palette.accentText : palette.textPrimary;

  const pill: ViewStyle = {
    paddingHorizontal: space.lg,
    paddingVertical:   space.sm,
    borderRadius:      radius.chip,
    backgroundColor:   pillBg,
    borderWidth:       StyleSheet.hairlineWidth,
    borderColor:       pillBorder,
    alignSelf:         "flex-start",
  };

  const content = (
    <Meta
      style={{ ...textTokens.chip, color: labelColor, textTransform: "uppercase" }}
    >
      {upper}
    </Meta>
  );

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [pill, pressed && { opacity: 0.7 }, style as StyleProp<ViewStyle>]}
        accessibilityRole="button"
        accessibilityLabel={`${upper} filter`}
        accessibilityState={{ selected: active }}
      >
        {content}
      </Pressable>
    );
  }

  return <View style={[pill, style as StyleProp<ViewStyle>]}>{content}</View>;
}

/** Renders multiple inline TopicChips separated by middle dots: "AI · BUSINESS". */
export function TopicChipRow({ topics, style }: { topics: string[]; style?: StyleProp<ViewStyle> }) {
  const { palette } = useTheme();
  if (topics.length === 0) return null;
  return (
    <View style={[{ flexDirection: "row", flexWrap: "wrap" }, style]}>
      {topics.map((t, i) => (
        <React.Fragment key={t}>
          <TopicChip label={t} mode="inline" />
          {i < topics.length - 1 && (
            <Meta
              style={{
                ...textTokens.chip,
                color: palette.accent,
                marginHorizontal: 4,
              }}
            >
              {"·"}
            </Meta>
          )}
        </React.Fragment>
      ))}
    </View>
  );
}
