/**
 * app/(tabs)/index.tsx — Top Stories tab.
 *
 * Header + FlatList of <StoryCard> (variant chosen per item). Cards tap-
 * navigate to /story/[id]. Pull-to-refresh, skeleton/empty/error states.
 *
 * Why a 168h window: we run one cron a day on a sometimes-bumpy OpenAI
 * billing pipeline; a 7-day window guarantees content even after a day
 * of failed synthesis. Once the pipeline has been clean for a few weeks
 * we can drop this back to 24-48h.
 */
import React from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { Body, Card, DisplayHL, Headline, Meta } from "../../components/ui";
import { StoryCard } from "../../components/StoryCard";
import { useTopStories } from "../../lib/hooks";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

export default function TopStoriesTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const { data, isLoading, isError, refetch, isRefetching } = useTopStories({
    hours: 168,
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
