/**
 * components/StoryCard/MultiStoryCard.tsx — full story card for multi-source stories.
 *
 * UI spec §3.2: topic chips · 3-line headline · 3-line summary preview ·
 * source-dot row + "N sources · Xh ago" meta. Tapping the card navigates to
 * the story detail screen.
 *
 * Visual hierarchy: this is the "wedge" — multi-source stories should feel
 * heavier than singletons (cf. SingletonCard), since cross-source corroboration
 * is the differentiating feature of Brevio. Phase G adds a left-edge peach
 * accent bar whose width scales with article_count (more sources = thicker
 * bar = visual "heat" cue), plus a soft peach wash from the left so the
 * bar feels like it's bleeding into the card rather than stuck on.
 */
import React from "react";
import { StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { Card, Headline, Meta, Preview, SourceDotRow, TopicChipRow } from "../ui";
import { formatRelativeTime } from "../../lib/time";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import type { StoryCard as StoryCardData } from "../../lib/api";

type Props = {
  story:   StoryCardData;
  onPress?: () => void;
  style?:   any;
};

export const MultiStoryCard = React.memo(MultiStoryCardImpl);

// Saturate the bar width so absurdly-large stories don't blow it up to a
// quarter of the card. Tier breakpoints by article_count are tuned to make
// "5 sources" visibly heavier than "2", but "20" not much heavier than "10".
function accentBarWidth(articleCount: number): number {
  if (articleCount >= 8)  return 6;
  if (articleCount >= 4)  return 5;
  return 4;
}

function MultiStoryCardImpl({ story, onPress, style }: Props) {
  const { palette } = useTheme();

  const ago = story.last_seen_at ? formatRelativeTime(story.last_seen_at) : "";
  const sourcesLabel = `${story.article_count} source${story.article_count === 1 ? "" : "s"}`;
  const a11yLabel = `${story.headline}. ${sourcesLabel}${ago ? `, ${ago}` : ""}.`;

  const barWidth = accentBarWidth(story.article_count);

  return (
    <Card onPress={onPress} style={style} accessibilityLabel={a11yLabel}>
      {/* Left-edge accent bar — solid peach. */}
      <View
        pointerEvents="none"
        style={[
          styles.accentBar,
          { width: barWidth, backgroundColor: palette.accent },
        ]}
      />

      {/* Soft peach wash bleeding inward from the bar, ~22% alpha → 0.
          Stops at ~25% of card width so headline / preview text on the
          right stays on a clean cardBg surface with full contrast. */}
      <LinearGradient
        pointerEvents="none"
        colors={[palette.accent + "26", palette.accent + "00"]}
        start={{ x: 0, y: 0.5 }}
        end={{ x: 0.25, y: 0.5 }}
        style={StyleSheet.absoluteFill}
      />

      {story.topics.length > 0 && (
        <TopicChipRow topics={story.topics} style={{ marginBottom: space.sm }} />
      )}

      <Headline numberOfLines={3} style={{ marginBottom: space.sm }}>
        {story.headline}
      </Headline>

      <Preview muted numberOfLines={3} style={{ marginBottom: space.md }}>
        {story.summary_preview}
      </Preview>

      <View style={styles.metaRow}>
        <SourceDotRow sources={story.source_ids} />
        <Meta muted style={{ color: palette.textMuted }}>
          {sourcesLabel}
          {ago ? ` · ${ago}` : ""}
        </Meta>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  metaRow: {
    flexDirection:  "row",
    alignItems:     "center",
    justifyContent: "space-between",
    gap:            space.sm,
  },
  accentBar: {
    position: "absolute",
    top:      0,
    bottom:   0,
    left:     0,
  },
});
