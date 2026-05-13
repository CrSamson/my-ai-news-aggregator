/**
 * app/story/[id].tsx — Story Detail screen.
 *
 * UI spec §6: the "moneymaker" screen. Layout:
 *   - Topic chips row
 *   - 28pt serif headline
 *   - "N sources · First reported Xd ago" meta
 *   - SUMMARY section (16pt body)
 *   - KEY POINTS section (bulleted)
 *   - TIMELINE — N SOURCES (vertical-rail chronology, oldest first)
 *
 * For singletons (article_count === 1):
 *   - Replace TIMELINE with a single SOURCE card.
 *   - If `summary` is empty (synthesis was skipped), the API already filled
 *     it from articles.summary or RSS description, so we don't branch here.
 *
 * Tapping a source card opens it in the in-app WebView (`/browser?url=...`).
 */
import React, { useMemo } from "react";
import { ActivityIndicator, ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";

import { Body, Card, DisplayHL, Headline, Meta, SectionLabel, TopicChipRow } from "../../components/ui";
import { Timeline } from "../../components/story/Timeline";
import { useStoryDetail } from "../../lib/hooks";
import { formatRelativeTime } from "../../lib/time";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import type { ArticleSource } from "../../lib/api";

export default function StoryDetailScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string }>();
  const storyId = Number(params.id);

  const { data: story, isLoading, isError, refetch } = useStoryDetail(storyId);

  // Sort member articles oldest→newest so the timeline reads chronologically.
  const sortedArticles = useMemo<ArticleSource[]>(() => {
    if (!story?.articles) return [];
    return [...story.articles].sort((a, b) => {
      const ta = a.published_at ? new Date(a.published_at).getTime() : 0;
      const tb = b.published_at ? new Date(b.published_at).getTime() : 0;
      return ta - tb;
    });
  }, [story?.articles]);

  const openArticle = (article: ArticleSource) => {
    router.push({
      pathname: "/browser",
      params: {
        url:    article.url,
        source: article.source_display_name ?? article.source,
      },
    });
  };

  if (isLoading || !story) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }}>
        <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
          {isError ? (
            <View style={{ padding: space.xl, alignItems: "center" }}>
              <Headline>Couldn't load story</Headline>
              <Body
                onPress={() => refetch()}
                accessibilityRole="button"
                accessibilityLabel="Retry loading story"
                style={{
                  marginTop:          space.sm,
                  color:              palette.accent,
                  textDecorationLine: "underline",
                }}
              >
                Tap to retry
              </Body>
            </View>
          ) : (
            <ActivityIndicator color={palette.accent} />
          )}
        </View>
      </SafeAreaView>
    );
  }

  const isMulti       = story.is_multi_source;
  const firstSeenAt   = story.first_seen_at;
  const firstReported = firstSeenAt ? formatRelativeTime(firstSeenAt) : "";
  const sourcesLabel  = `${story.article_count} source${story.article_count === 1 ? "" : "s"}`;
  const metaLine      = firstReported
    ? `${sourcesLabel} · First reported ${firstReported}`
    : sourcesLabel;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["bottom"]}>
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: space.xl,
          paddingBottom:     space.xxxl * 2,
          paddingTop:        space.sm,
        }}
      >
        {story.topics.length > 0 && (
          <TopicChipRow topics={story.topics} style={{ marginBottom: space.md }} />
        )}

        <DisplayHL style={{ marginBottom: space.md }}>
          {story.headline}
        </DisplayHL>

        <Meta muted style={{ marginBottom: space.xl }}>
          {metaLine}
        </Meta>

        {/* SUMMARY */}
        {story.summary?.length > 0 && (
          <View style={{ marginBottom: space.xl }}>
            <SectionLabel muted style={{ marginBottom: space.sm }}>SUMMARY</SectionLabel>
            <Body>{story.summary}</Body>
          </View>
        )}

        {/* KEY POINTS */}
        {story.key_points.length > 0 && (
          <View style={{ marginBottom: space.xl }}>
            <SectionLabel muted style={{ marginBottom: space.sm }}>KEY POINTS</SectionLabel>
            {story.key_points.map((point, i) => (
              <View
                key={i}
                style={{
                  flexDirection: "row",
                  marginBottom:  space.sm,
                  alignItems:    "flex-start",
                }}
              >
                <Body style={{ color: palette.accent, marginRight: space.sm }}>•</Body>
                <Body style={{ flex: 1 }}>{point}</Body>
              </View>
            ))}
          </View>
        )}

        {/* TIMELINE / SOURCE */}
        <View style={{ marginBottom: space.xl }}>
          <SectionLabel muted style={{ marginBottom: space.md }}>
            {isMulti ? `TIMELINE — ${story.article_count} SOURCES` : "SOURCE"}
          </SectionLabel>

          {isMulti ? (
            <Timeline articles={sortedArticles} onPressArticle={openArticle} />
          ) : sortedArticles[0] ? (
            <Card soft onPress={() => openArticle(sortedArticles[0])}>
              <SectionLabel style={{ color: palette.accent }}>
                {(sortedArticles[0].source_display_name ?? sortedArticles[0].source).toUpperCase()}
              </SectionLabel>
              {sortedArticles[0].published_at && (
                <Meta muted style={{ marginTop: space.xs }}>
                  {formatRelativeTime(sortedArticles[0].published_at)}
                </Meta>
              )}
              <Headline numberOfLines={3} style={{ marginTop: space.sm, fontSize: 16, lineHeight: 22 }}>
                {sortedArticles[0].title}
              </Headline>
              {sortedArticles[0].author && (
                <Meta muted style={{ marginTop: space.xs }}>By {sortedArticles[0].author}</Meta>
              )}
              <Body
                accessibilityRole="link"
                style={{
                  marginTop:          space.sm,
                  color:              palette.accent,
                  textDecorationLine: "underline",
                }}
              >
                Read on {sortedArticles[0].source_display_name ?? sortedArticles[0].source.replace(/_/g, " ")} →
              </Body>
            </Card>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
