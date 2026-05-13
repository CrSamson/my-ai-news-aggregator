/**
 * app/(tabs)/all.tsx — All News tab.
 *
 * UI spec §5: chronological feed of all stories in the last 48h, mixing
 * multi-source and singletons sorted purely by recency (last_seen_at DESC).
 * No topic filter, no scoring — just the firehose.
 *
 * Same <StoryCard> dispatcher as the Top tab, same navigation to detail.
 */
import React from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { Body, Card, DisplayHL, Headline, Meta } from "../../components/ui";
import { StoryCard } from "../../components/StoryCard";
import { useAllStories } from "../../lib/hooks";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

const WINDOW_HOURS = 48;

export default function AllNewsTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const { data, isLoading, isError, refetch, isRefetching } = useAllStories({
    hours: WINDOW_HOURS,
    limit: 100,
  });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <FlatList
        data={data?.items ?? []}
        keyExtractor={(item) => `all-${item.id}`}
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
            <DisplayHL>All News</DisplayHL>
            <Meta muted style={{ marginTop: space.xs }}>
              Last {WINDOW_HOURS} hours
              {data?.total_in_window != null ? ` · ${data.total_in_window} stories` : ""}
            </Meta>
          </View>
        }
        ListEmptyComponent={
          isLoading ? (
            <Card static>
              <Body muted>Loading…</Body>
            </Card>
          ) : isError ? (
            <Card static>
              <Headline>Couldn't reach Brevio</Headline>
              <Body muted style={{ marginTop: space.sm }}>Pull down to retry.</Body>
            </Card>
          ) : (
            <Card static>
              <Body muted>No stories in the last {WINDOW_HOURS} hours.</Body>
            </Card>
          )
        }
        ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
        renderItem={({ item }) => (
          <StoryCard
            story={item}
            onPress={() =>
              router.push({ pathname: "/story/[id]", params: { id: String(item.id) } })
            }
          />
        )}
      />
    </SafeAreaView>
  );
}
