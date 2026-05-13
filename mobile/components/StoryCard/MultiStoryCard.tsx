/**
 * components/StoryCard/MultiStoryCard.tsx — full story card for multi-source stories.
 *
 * UI spec §3.2: topic chips · 3-line headline · 3-line summary preview ·
 * source-dot row + "N sources · Xh ago" meta. Tapping the card navigates to
 * the story detail screen.
 *
 * Visual hierarchy: this is the "wedge" — multi-source stories should feel
 * heavier than singletons (cf. SingletonCard), since cross-source corroboration
 * is the differentiating feature of Brevio.
 */
import React from "react";
import { StyleSheet, View } from "react-native";

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

export function MultiStoryCard({ story, onPress, style }: Props) {
  const { palette } = useTheme();

  const ago = story.last_seen_at ? formatRelativeTime(story.last_seen_at) : "";
  const sourcesLabel = `${story.article_count} source${story.article_count === 1 ? "" : "s"}`;

  return (
    <Card onPress={onPress} style={style}>
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
});
