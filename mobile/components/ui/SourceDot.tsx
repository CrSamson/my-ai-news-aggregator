/**
 * components/ui/SourceDot.tsx — colored circle marking one source publisher.
 *
 * UI spec §3.2: small filled circles, one per source publisher, brand color
 * if known else gray. <SourceDotRow> shows up to 4 + "+N" overflow.
 */
import React from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";

import { colorForSource, space, text as textTokens } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { Meta } from "./Text";

type Props = {
  source: string;
  size?:  number;
  style?: ViewStyle;
};

export function SourceDot({ source, size = 10, style }: Props) {
  const { palette } = useTheme();
  const color = colorForSource(source, palette.textMuted);
  return (
    <View
      style={[
        {
          width:           size,
          height:          size,
          borderRadius:    size / 2,
          backgroundColor: color,
          borderWidth:     StyleSheet.hairlineWidth,
          borderColor:     palette.border,
        },
        style,
      ]}
      accessibilityLabel={`Source: ${source}`}
    />
  );
}

type RowProps = {
  sources:     string[];
  maxVisible?: number;
  dotSize?:    number;
  style?:      ViewStyle;
};

export function SourceDotRow({
  sources,
  maxVisible = 4,
  dotSize = 10,
  style,
}: RowProps) {
  const { palette } = useTheme();
  if (sources.length === 0) return null;

  const visible  = sources.slice(0, maxVisible);
  const overflow = Math.max(0, sources.length - maxVisible);

  return (
    <View style={[{ flexDirection: "row", alignItems: "center" }, style]}>
      {visible.map((s, i) => (
        <SourceDot
          key={`${s}-${i}`}
          source={s}
          size={dotSize}
          style={{ marginRight: i < visible.length - 1 ? 4 : 0 }}
        />
      ))}
      {overflow > 0 && (
        <Meta
          style={{
            ...textTokens.meta,
            color: palette.textMuted,
            marginLeft: space.xs,
          }}
        >
          +{overflow}
        </Meta>
      )}
    </View>
  );
}
