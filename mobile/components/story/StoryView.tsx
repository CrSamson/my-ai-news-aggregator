/**
 * components/story/StoryView.tsx — single-story detail render.
 *
 * Pulled out of app/story/[id].tsx so the pager doesn't duplicate layout.
 *
 * Phase H3: full-bleed peach gradient hero at the top — headline + meta
 * sit on the same gradient as the app icon (cohesive brand surface).
 * Below the hero, body sections (chips, summary, key points, timeline)
 * sit on the cream bg with the normal text contrast.
 */
import React, { useMemo } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";

import { Body, Card, DisplayHL, Headline, Meta, SectionLabel, TopicChipRow } from "../ui";
import { Timeline } from "./Timeline";
import { useStoryDetail } from "../../lib/hooks";
import { formatRelativeTime } from "../../lib/time";
import { fonts, space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import type { ArticleSource } from "../../lib/api";

// Gradient endpoints match tools/make_pwa_icons.py so the hero feels like
// it was painted on the same canvas as the app icon.
const HERO_FROM = "#F2A883";
const HERO_TO   = "#D87550";

type Props = {
  storyId: number;
  width:   number;
};

export function StoryView({ storyId, width }: Props) {
  const { palette } = useTheme();
  const router = useRouter();

  const { data: story, isLoading, isError, refetch } = useStoryDetail(storyId);

  const sortedArticles = useMemo<ArticleSource[]>(() => {
    if (!story?.articles) return [];
    return [...story.articles].sort((a, b) => {
      const ta = a.published_at ? new Date(a.published_at).getTime() : 0;
      const tb = b.published_at ? new Date(b.published_at).getTime() : 0;
      return ta - tb;
    });
  }, [story?.articles]);

  const openArticle = (article: ArticleSource) =>
    router.push({
      pathname: "/browser",
      params: {
        url:    article.url,
        source: article.source_display_name ?? article.source,
      },
    });

  if (isLoading || !story) {
    return (
      <View style={{ width, flex: 1, justifyContent: "center", alignItems: "center" }}>
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
    );
  }

  const isMulti       = story.is_multi_source;
  const firstReported = story.first_seen_at ? formatRelativeTime(story.first_seen_at) : "";
  const sourcesLabel  = `${story.article_count} source${story.article_count === 1 ? "" : "s"}`;
  const metaLine      = firstReported
    ? `${sourcesLabel} · First reported ${firstReported}`
    : sourcesLabel;

  return (
    <ScrollView
      style={{ width }}
      contentContainerStyle={{ paddingBottom: space.xxxl * 2 }}
      showsVerticalScrollIndicator={false}
    >
      {/* HERO — full-bleed peach gradient, cream text. */}
      <LinearGradient
        colors={[HERO_FROM, HERO_TO]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.hero}
      >
        <Meta
          style={{
            color:        "#FAF5EECC",
            fontFamily:   fonts.sansSemibold,
            letterSpacing: 1.2,
          }}
        >
          {sourcesLabel.toUpperCase()}
        </Meta>
        <DisplayHL style={{ color: "#FAF5EE", marginTop: space.sm }}>
          {story.headline}
        </DisplayHL>
        {firstReported && (
          <Meta style={{ color: "#FAF5EECC", marginTop: space.md }}>
            First reported {firstReported}
          </Meta>
        )}
      </LinearGradient>

      <View style={styles.body}>
        {story.topics.length > 0 && (
          <TopicChipRow topics={story.topics} style={{ marginBottom: space.xl }} />
        )}

        {story.summary?.length > 0 && (
          <View style={{ marginBottom: space.xl }}>
            <SectionLabel muted style={{ marginBottom: space.sm }}>SUMMARY</SectionLabel>
            <Body>{story.summary}</Body>
          </View>
        )}

        {story.key_points.length > 0 && (
          <View style={{ marginBottom: space.xl }}>
            <SectionLabel muted style={{ marginBottom: space.sm }}>KEY POINTS</SectionLabel>
            {story.key_points.map((point, i) => (
              <View
                key={i}
                style={{ flexDirection: "row", marginBottom: space.sm, alignItems: "flex-start" }}
              >
                <Body style={{ color: palette.accent, marginRight: space.sm }}>•</Body>
                <Body style={{ flex: 1 }}>{point}</Body>
              </View>
            ))}
          </View>
        )}

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
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  hero: {
    paddingHorizontal: space.xl,
    paddingTop:        space.xl,
    paddingBottom:     space.xxxl,
  },
  body: {
    paddingHorizontal: space.xl,
    paddingTop:        space.xl,
  },
});
