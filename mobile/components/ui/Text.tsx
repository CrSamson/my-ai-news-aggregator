/**
 * components/ui/Text.tsx — typography primitives.
 *
 * Wrappers around React Native's <Text> that apply Brevio's text styles
 * + theme color. Variants map 1:1 to UI spec §1.1 + §3.2 + §6.1.
 *
 * <Headline>      story-card headline (serif 20pt)
 * <DisplayHL>     story-detail headline (serif 28pt)
 * <Body>          16pt sans, 1.6 line-height
 * <Preview>       14pt summary preview
 * <Meta>          12pt muted metadata
 * <SectionLabel>  11pt uppercase ("SUMMARY", "TIMELINE", ...)
 */
import React from "react";
import { Text as RNText, type TextProps, type TextStyle } from "react-native";

import { text } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type Variant = keyof typeof text;

type Props = TextProps & {
  variant?: Variant;
  muted?:   boolean;     // use textMuted instead of textPrimary
  color?:   string;      // explicit override
};

function makeText(variant: Variant) {
  return function ({ muted, color, style, children, ...rest }: Props) {
    const { palette } = useTheme();
    const fallback = muted ? palette.textMuted : palette.textPrimary;
    const styles: TextStyle = {
      ...text[variant],
      color: color ?? fallback,
    };
    return (
      <RNText {...rest} style={[styles, style]}>
        {children}
      </RNText>
    );
  };
}

export const DisplayHL    = makeText("displayLg");
export const Headline     = makeText("headline");
export const Body         = makeText("body");
export const Preview      = makeText("preview");
export const Meta         = makeText("meta");
export const SectionLabel = makeText("sectionLabel");
