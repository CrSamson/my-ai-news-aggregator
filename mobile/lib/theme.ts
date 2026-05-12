/**
 * lib/theme.ts — Brevio design tokens.
 *
 * Single source of truth for colors, typography, spacing, radius.
 * Components import { useTheme } here rather than hard-coding values,
 * so a future palette tweak or new dark-mode shade lands in one file.
 *
 * Driven by the OS color scheme (`useColorScheme()` from react-native).
 * No in-app toggle per UI spec §1.1 & §10.
 */

export type ColorScheme = "light" | "dark";

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------

export type Palette = {
  bg:          string;     // page background
  cardBg:      string;     // story card surface
  cardBgSoft:  string;     // tinted inner surface (e.g. timeline source cards)
  textPrimary: string;     // body + headline copy
  textMuted:   string;     // metadata + secondary
  border:      string;     // 1px hairlines (replaces shadow per spec §1.2)
  accent:      string;     // peach — used SPARINGLY (active chips, brand mark)
  accentText:  string;     // text color when on accent background
};

const LIGHT: Palette = {
  bg:          "#FAF5EE",
  cardBg:      "#FFFFFF",
  cardBgSoft:  "#F4EEE4",
  textPrimary: "#1A1410",
  textMuted:   "#7A6E68",
  border:      "#EBE4D8",
  accent:      "#EE9970",
  accentText:  "#FFFFFF",
};

const DARK: Palette = {
  bg:          "#1A1410",
  cardBg:      "#2A1F1A",
  cardBgSoft:  "#3A2D26",
  textPrimary: "#F6BFA1",
  textMuted:   "#9B8D85",
  border:      "#3A2D26",
  accent:      "#EE9970",
  accentText:  "#1A1410",
};

export const palette = (scheme: ColorScheme): Palette =>
  scheme === "dark" ? DARK : LIGHT;

// ---------------------------------------------------------------------------
// Typography
// ---------------------------------------------------------------------------
// Fonts loaded in app/_layout.tsx via @expo-google-fonts/lora and inter.
// Use the family names exposed by those packages.

export const fonts = {
  serif:        "Lora_500Medium",
  serifBold:    "Lora_700Bold",
  sans:         "Inter_400Regular",
  sansMedium:   "Inter_500Medium",
  sansSemibold: "Inter_600SemiBold",
  // System fallback while custom fonts load — keeps the first paint legible.
  sansFallback: undefined as unknown as string,
} as const;

export const text = {
  // Story-detail headline (28pt per UI spec §6.1).
  displayLg: { fontFamily: fonts.serifBold, fontSize: 28, lineHeight: 34 },
  // Story-card headline (20pt per UI spec §3.2).
  headline:  { fontFamily: fonts.serifBold, fontSize: 20, lineHeight: 26 },
  // Body copy in story-detail (16pt, 1.6 line-height per UI spec §6.1).
  body:      { fontFamily: fonts.sans,      fontSize: 16, lineHeight: 26 },
  // Card preview (14pt per UI spec §3.2 summary preview).
  preview:   { fontFamily: fonts.sans,      fontSize: 14, lineHeight: 20 },
  // Metadata line (12pt per UI spec §3.2).
  meta:      { fontFamily: fonts.sans,      fontSize: 12, lineHeight: 16 },
  // Topic chip (10pt uppercase per UI spec §3.2).
  chip:      { fontFamily: fonts.sansSemibold, fontSize: 10, lineHeight: 14, letterSpacing: 0.6 },
  // Section header in detail view (11pt uppercase per UI spec §6.1).
  sectionLabel: { fontFamily: fonts.sansSemibold, fontSize: 11, lineHeight: 14, letterSpacing: 1.2 },
} as const;

// ---------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  card:   14,
  chip:   12,
  button:  8,
} as const;

// ---------------------------------------------------------------------------
// Source-publisher brand colors
// ---------------------------------------------------------------------------
// Used for the source-dot row on story cards (UI spec §3.2). Unmapped
// sources fall back to a neutral grey (the theme's textMuted).
// Phase G1 moves this to backend (sources.json `brand_color` field).

export const sourceColors: Record<string, string> = {
  // AI labs — peach to match our brand on Anthropic, then official-ish brand colors
  anthropic_news:        "#EE9970",
  anthropic_research:    "#EE9970",
  anthropic_engineering: "#EE9970",
  openai_news:           "#10A37F",
  google_research:       "#4285F4",
  aws_ml:                "#FF9900",
  nvidia_developer:      "#76B900",
  meta_ai:               "#0866FF",
  bair:                  "#003262",
  cmu_ml:                "#C41230",
  mit_news:              "#A31F34",

  // Specialist tech / science press
  techcrunch_ai:         "#0A9F00",
  the_verge:             "#5200FF",
  ars_technica:          "#FF4B00",
  wired:                 "#000000",
  nature:                "#006633",
  sciencedaily:          "#FF6633",
  phys_org:              "#1E5288",
  quanta:                "#E84E1B",

  // Major news outlets
  bbc_news:              "#B92223",
  cnbc:                  "#005594",
  the_independent:       "#EE2A24",
  cna:                   "#00B5E2",
  forbes_business:       "#000000",
  yahoo_finance:         "#720E9E",
  cbc_news:              "#E60000",
  air_space_forces:      "#003366",
};

export const colorForSource = (source: string, fallback: string): string => {
  return sourceColors[source] ?? fallback;
};
