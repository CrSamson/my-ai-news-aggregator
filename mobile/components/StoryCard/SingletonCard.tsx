/**
 * components/StoryCard/SingletonCard.tsx — quieter card for single-source stories.
 *
 * UI spec §3.3: smaller, lighter visual weight than MultiStoryCard so the
 * multi-source "wedge" stays visually dominant in mixed lists. Shows:
 *   - 1 topic chip
 *   - Headline (3 lines max)
 *   - Summary (2 lines)
 *   - Inline source dot + publisher + time on one line (not a dot row)
 *
 * Used both in the Top Stories tab tail and in the Topics tab "singleton
 * top picks" row.
 */
import React from "react";
import { StyleSheet, View } from "react-native";

import { Card, Headline, Meta, Preview, SourceDot, TopicChip } from "../ui";
import { formatRelativeTime } from "../../lib/time";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import type { StoryCard as StoryCardData } from "../../lib/api";

type Props = {
  story:   StoryCardData;
  onPress?: () => void;
  style?:   any;
};

export const SingletonCard = React.memo(SingletonCardImpl);

function SingletonCardImpl({ story, onPress, style }: Props) {
  const { palette } = useTheme();
  const primaryTopic = story.topics[0];
  const source       = story.primary_source ?? story.source_ids[0] ?? "";
  const ago          = story.last_seen_at ? formatRelativeTime(story.last_seen_at) : "";
  const a11yLabel    = `${story.headline}.${source ? ` ${source.replace(/_/g, " ")}` : ""}${ago ? `, ${ago}` : ""}.`;

  return (
    <Card onPress={onPress} style={style} padding={space.lg} accessibilityLabel={a11yLabel}>
      {primaryTopic && (
        <TopicChip label={primaryTopic} mode="inline" style={{ marginBottom: space.xs }} />
      )}

      <Headline numberOfLines={3} style={{ marginBottom: space.xs, fontSize: 18, lineHeight: 24 }}>
        {story.headline}
      </Headline>

      <Preview muted numberOfLines={2} style={{ marginBottom: space.sm }}>
        {story.summary_preview}
      </Preview>

      <View style={styles.metaRow}>
        {source ? <SourceDot source={source} size={8} /> : null}
        <Meta muted style={{ color: palette.textMuted }}>
          {source ? source.replace(/_/g, " ") : "Source"}
          {ago ? ` · ${ago}` : ""}
        </Meta>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  metaRow: {
    flexDirection: "row",
    alignItems:    "center",
    gap:           space.xs,
  },
});
