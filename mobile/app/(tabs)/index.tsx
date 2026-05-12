/**
 * app/(tabs)/index.tsx — Top Stories tab (placeholder for Phase B).
 *
 * Phase B scope: load real data via useTopStories(), render a count + a
 * minimal preview. The full Story Card UI (multi-source vs singleton
 * variants, source dots, fade-out preview) lands in Phase C.
 *
 * The point of this Phase B scaffold is to prove end-to-end:
 *   theme → fonts → tabs nav → API client → React Query → UI
 */
import React from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  Body,
  Card,
  DisplayHL,
  Headline,
  Meta,
  Preview,
  SourceDotRow,
  TopicChipRow,
} from "../../components/ui";
import { useTopStories } from "../../lib/hooks";
import { formatRelativeTime } from "../../lib/time";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

export default function TopStoriesTab() {
  const { palette } = useTheme();
  const { data, isLoading, isError, refetch, isRefetching } = useTopStories({
    hours: 168,    // 7-day window so we see meaningful data while OpenAI billing is pending
    limit: 20,
  });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <FlatList
        data={data?.items ?? []}
        keyExtractor={(item) => `story-${item.id}`}
        contentContainerStyle={{ padding: space.xl, paddingBottom: space.xxxl }}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={palette.accent}
          />
        }
        ListHeaderComponent={
          <View style={{ marginBottom: space.xl }}>
            <DisplayHL style={{ color: palette.accent }}>Brevio</DisplayHL>
            <Meta muted style={{ marginTop: space.xs }}>
              {new Date().toLocaleDateString(undefined, {
                weekday: "long",
                month:   "long",
                day:     "numeric",
              })}
            </Meta>
          </View>
        }
        ListEmptyComponent={
          isLoading ? (
            <Card static>
              <Body muted>Loading top stories…</Body>
            </Card>
          ) : isError ? (
            <Card static>
              <Headline>Couldn't reach Brevio</Headline>
              <Body muted style={{ marginTop: space.sm }}>
                Pull down to retry.
              </Body>
            </Card>
          ) : (
            <Card static>
              <Body muted>No stories in the last 7 days yet.</Body>
            </Card>
          )
        }
        renderItem={({ item }) => (
          <Card style={{ marginBottom: space.lg }}>
            <TopicChipRow topics={item.topics} style={{ marginBottom: space.sm }} />
            <Headline numberOfLines={3} style={{ marginBottom: space.sm }}>
              {item.headline}
            </Headline>
            <Preview muted numberOfLines={3} style={{ marginBottom: space.md }}>
              {item.summary_preview}
            </Preview>
            <View style={styles.metaRow}>
              <SourceDotRow sources={item.source_ids} />
              <Meta muted>
                {item.article_count} source{item.article_count === 1 ? "" : "s"}
                {item.last_seen_at ? ` · ${formatRelativeTime(item.last_seen_at)}` : ""}
              </Meta>
            </View>
          </Card>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  metaRow: {
    flexDirection: "row",
    alignItems:    "center",
    justifyContent: "space-between",
    gap:           space.sm,
  },
});
