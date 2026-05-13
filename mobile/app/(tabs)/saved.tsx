/**
 * app/(tabs)/saved.tsx — saved-stories tab.
 *
 * Read-only view of stories the user has bookmarked. The list is the
 * saved-ID set (newest-first by ID, which corresponds to "most recently
 * synthesised" — close enough to "most recent" without storing timestamps).
 * Each row pulls its data from the React Query cache; the screen will
 * lazily re-fetch any IDs whose cache entry has gone stale (5-min TTL).
 *
 * Empty state has its own personality so the screen doesn't read as
 * "broken" to new users who haven't saved anything yet.
 */
import React, { useMemo } from "react";
import { FlatList, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQueries } from "@tanstack/react-query";

import { Body, Card, DisplayHL, Meta } from "../../components/ui";
import { StoryCard } from "../../components/StoryCard";
import { useSavedStories } from "../../lib/saved";
import { api, type StoryDetail } from "../../lib/api";
import { qk } from "../../lib/hooks";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

export default function SavedTab() {
  const { palette } = useTheme();
  const router      = useRouter();
  const { ids, count, ready } = useSavedStories();

  // Newest-first by ID. Auto-incrementing PKs in Postgres give us a free
  // chronological sort here without persisting a saved-at timestamp.
  const idsArr = useMemo(() => [...ids].sort((a, b) => b - a), [ids]);

  // Parallel fetch of every saved story's detail. React Query dedupes —
  // anything already viewed is served from cache instantly.
  const results = useQueries({
    queries: idsArr.map((id) => ({
      queryKey:   qk.storyDetail(id),
      queryFn:    ({ signal }: { signal?: AbortSignal }) => api.storyDetail(id, signal),
      staleTime:  5 * 60 * 1_000,
      gcTime:     60 * 60 * 1_000,
      enabled:    Number.isFinite(id) && id > 0,
    })),
  });

  // StoryDetail extends StoryCard, so we can hand the detail straight to
  // <StoryCard>. Filter out queries that haven't returned yet.
  const stories = useMemo(
    () => results.map((r) => r.data).filter((d): d is StoryDetail => !!d),
    [results],
  );

  const queueParam = stories.map((s) => s.id).join(",");

  const openStory = (id: number) =>
    router.push({
      pathname: "/story/[id]",
      params:   { id: String(id), queue: queueParam },
    });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <FlatList
        data={stories}
        keyExtractor={(item) => `saved-${item.id}`}
        contentContainerStyle={{ padding: space.xl, paddingBottom: space.xxxl }}
        initialNumToRender={6}
        maxToRenderPerBatch={6}
        windowSize={9}
        ListHeaderComponent={
          <View style={{ marginBottom: space.xl }}>
            <DisplayHL>Saved</DisplayHL>
            <Meta muted style={{ marginTop: space.xs }}>
              {count === 0
                ? "Stories you bookmark appear here"
                : `${count} stor${count === 1 ? "y" : "ies"}`}
            </Meta>
          </View>
        }
        ListEmptyComponent={
          !ready ? (
            <Card static>
              <Body muted>Loading…</Body>
            </Card>
          ) : (
            <Card static>
              <Body muted>
                No saved stories yet. Tap the bookmark icon on any story
                detail to save it for later — they'll wait here for you.
              </Body>
            </Card>
          )
        }
        ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
        renderItem={({ item }) => (
          <StoryCard story={item} onPress={() => openStory(item.id)} />
        )}
      />
    </SafeAreaView>
  );
}
