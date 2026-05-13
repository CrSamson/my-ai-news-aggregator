/**
 * components/ui/Card.tsx — themed card container.
 *
 * Rounded surface that "lifts" via background-contrast against the cream
 * page bg, not via shadow (per UI spec §1.2 "no drop shadows beyond a 1-2px
 * subtle separator"). Press state is a quiet background flash for tap-down
 * feedback (spec §3.2).
 */
import React from "react";
import {
  Pressable,
  StyleSheet,
  View,
  type PressableProps,
  type ViewStyle,
} from "react-native";

import { radius, space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type Props = PressableProps & {
  /** Use the slightly-tinted variant — for source cards inside the timeline. */
  soft?:    boolean;
  /** Override the default 20px internal padding. */
  padding?: number;
  /** Render as a non-pressable static card. */
  static?:  boolean;
  style?:   ViewStyle;
  children?: React.ReactNode;
};

export function Card({
  soft = false,
  padding = space.xl,
  static: isStatic = false,
  style,
  children,
  ...rest
}: Props) {
  const { palette } = useTheme();
  const surface = soft ? palette.cardBgSoft : palette.cardBg;
  const baseStyle: ViewStyle = {
    backgroundColor: surface,
    borderRadius:    radius.card,
    padding,
    borderWidth:     StyleSheet.hairlineWidth,
    borderColor:     palette.border,
  };

  if (isStatic) {
    return <View style={[baseStyle, style]}>{children}</View>;
  }

  return (
    <Pressable
      accessibilityRole="button"
      {...rest}
      style={({ pressed }) => [
        baseStyle,
        pressed && { opacity: 0.85 },
        style,
      ]}
    >
      {children}
    </Pressable>
  );
}
