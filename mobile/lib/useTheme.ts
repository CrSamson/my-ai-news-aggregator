/**
 * lib/useTheme.ts — React hook that returns the active palette + a helper
 * to construct themed StyleSheet objects.
 *
 * Usage:
 *   const { palette, scheme } = useTheme();
 *   <Text style={{ color: palette.textPrimary }}>…</Text>
 *
 * Driven by the OS color scheme. No in-app toggle.
 */
import { useColorScheme as useRNColorScheme } from "react-native";
import { palette as paletteFor, type ColorScheme, type Palette } from "./theme";

export type ThemeContext = {
  scheme:  ColorScheme;
  palette: Palette;
};

export function useTheme(): ThemeContext {
  const sysScheme = useRNColorScheme();
  const scheme: ColorScheme = sysScheme === "dark" ? "dark" : "light";
  return {
    scheme,
    palette: paletteFor(scheme),
  };
}
