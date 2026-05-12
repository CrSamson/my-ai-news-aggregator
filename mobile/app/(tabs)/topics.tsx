/**
 * app/(tabs)/topics.tsx — Topics tab.
 *
 * Phase B scope: horizontal filter-chip row + count display. Real list
 * rendering ships in Phase D.
 */
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Body, Card, DisplayHL, Meta, TopicChip } from "../../components/ui";
import { TOPICS, type Topic } from "../../lib/api";
import { useTopicFeed } from "../../lib/hooks";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

export default function TopicsTab() {
  const { palette } = useTheme();
  const [topic, setTopic] = useState<Topic>("ai");
  const { data, isLoading } = useTopicFeed(topic, { hours: 720, singletons_n: 5 });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
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

      <View style={{ paddingHorizontal: space.xl }}>
        <Card static>
          <Body muted>
            {isLoading
              ? "Loading…"
              : `Showing ${data?.multi_stories.length ?? 0} multi-source ` +
                `+ ${data?.top_singletons.length ?? 0} top singletons for ` +
                `${topic.toUpperCase()}.`}
          </Body>
          <Meta muted style={{ marginTop: space.sm }}>
            Full topic-card UI lands in Phase D.
          </Meta>
        </Card>
      </View>
    </SafeAreaView>
  );
}
