/**
 * app/(tabs)/topics.tsx — Topics tab.
 *
 * UI spec §4: a horizontal row of topic filter chips at the top, then the
 * story feed for the selected topic below. The feed is two sections:
 *
 *   1. Multi-source stories (the "wedge") — sorted by article_count DESC.
 *   2. "TOP SINGLETONS" — the 5 highest-ranked singletons for the topic,
 *      chosen by agent.singleton_ranker so the section doesn't drown in
 *      low-signal one-off coverage.
 *
 * Both sections render <StoryCard>, which picks the right visual variant.
 */
import React, { useMemo, useState } from "react";
import { FlatList, RefreshControl, ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { Body, Card, DisplayHL, Headline, Meta, SectionLabel, TopicChip } from "../../components/ui";
import { StoryCard } from "../../components/StoryCard";
import { TOPICS, type StoryCard as StoryCardData, type Topic } from "../../lib/api";
import { useTopicFeed } from "../../lib/hooks";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type FeedRow =
  | { kind: "section"; key: string; label: string }
  | { kind: "story";   key: string; story: StoryCardData };

export default function TopicsTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const [topic, setTopic] = useState<Topic>("ai");

  const { data, isLoading, isError, refetch, isRefetching } = useTopicFeed(topic, {
    hours:        720,    // 30-day window so each topic has enough material
    multi_limit:  20,
    singletons_n: 5,
  });

  // Flatten multi_stories + top_singletons into one FlatList with section
  // headers — keeps virtualisation while still letting us label the two
  // halves of the feed.
  const rows = useMemo<FeedRow[]>(() => {
    if (!data) return [];
    const out: FeedRow[] = [];

    if (data.multi_stories.length > 0) {
      out.push({ kind: "section", key: "sec-multi", label: "MULTI-SOURCE STORIES" });
      data.multi_stories.forEach((s) =>
        out.push({ kind: "story", key: `multi-${s.id}`, story: s }),
      );
    }

    if (data.top_singletons.length > 0) {
      out.push({ kind: "section", key: "sec-single", label: "TOP SINGLETONS" });
      data.top_singletons.forEach((s) =>
        out.push({ kind: "story", key: `single-${s.id}`, story: s }),
      );
    }

    return out;
  }, [data]);

  const openStory = (id: number) =>
    router.push({ pathname: "/story/[id]", params: { id: String(id) } });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <FlatList
        data={rows}
        keyExtractor={(row) => row.key}
        contentContainerStyle={{ paddingBottom: space.xxxl }}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={palette.accent}
          />
        }
        ListHeaderComponent={
          <View>
            <View style={{ paddingHorizontal: space.xl, paddingTop: space.xl }}>
              <DisplayHL>Topics</DisplayHL>
            </View>

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{
                paddingHorizontal: space.xl,
                paddingVertical:   space.lg,
                gap:               space.sm,
              }}
            >
              {TOPICS.map((t) => (
                <TopicChip
                  key={t}
                  label={t}
                  mode="filter"
                  active={t === topic}
                  onPress={() => setTopic(t)}
                />
              ))}
            </ScrollView>
          </View>
        }
        ListEmptyComponent={
          <View style={{ paddingHorizontal: space.xl }}>
            {isLoading ? (
              <Card static>
                <Body muted>Loading {topic.toUpperCase()}…</Body>
              </Card>
            ) : isError ? (
              <Card static>
                <Headline>Couldn't reach Brevio</Headline>
                <Body muted style={{ marginTop: space.sm }}>Pull down to retry.</Body>
              </Card>
            ) : (
              <Card static>
                <Body muted>No {topic.toUpperCase()} stories in the last 30 days yet.</Body>
              </Card>
            )}
          </View>
        }
        ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
        renderItem={({ item }) => {
          if (item.kind === "section") {
            return (
              <View style={{ paddingHorizontal: space.xl, paddingTop: space.md }}>
                <SectionLabel muted>{item.label}</SectionLabel>
                {item.label === "TOP SINGLETONS" && (
                  <Meta muted style={{ marginTop: space.xs }}>
                    Highest-signal single-source stories this month.
                  </Meta>
                )}
              </View>
            );
          }
          return (
            <View style={{ paddingHorizontal: space.xl }}>
              <StoryCard story={item.story} onPress={() => openStory(item.story.id)} />
            </View>
          );
        }}
      />
    </SafeAreaView>
  );
}
