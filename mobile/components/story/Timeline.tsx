/**
 * components/story/Timeline.tsx — vertical-rail chronology of a story's sources.
 *
 * UI spec §6.1 + §6.2: 1px peach rail down the left with a filled dot at each
 * card's position; source cards laid out chronologically (oldest first). The
 * oldest card carries a subtle "FIRST REPORTED" badge — the only role label
 * we surface in MVP (full role classification is Phase G2 backend work).
 *
 * Tapping a card opens the article in the in-app WebView browser (Phase C4).
 */
import React from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { Body, Headline, Meta, SectionLabel } from "../ui";
import { fonts, radius, space, text as textTokens } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { formatRelativeTime } from "../../lib/time";
import type { ArticleSource } from "../../lib/api";

const RAIL_WIDTH      = 1;
const RAIL_INSET      = 8;        // x-offset of the rail from the row's left edge
const DOT_SIZE        = 10;
const CARD_TOP_OFFSET = 6;        // dot sits this far down from the card's top edge

type Props = {
  articles:        ArticleSource[];  // assumed sorted chronologically (oldest first)
  onPressArticle?: (article: ArticleSource) => void;
};

export function Timeline({ articles, onPressArticle }: Props) {
  const { palette } = useTheme();

  if (articles.length === 0) return null;

  return (
    <View>
      {articles.map((article, i) => {
        const isFirst = i === 0;
        const isLast  = i === articles.length - 1;

        return (
          <TimelineRow
            key={article.id}
            article={article}
            isFirstReported={isFirst}
            isLast={isLast}
            railColor={palette.accent}
            onPress={onPressArticle ? () => onPressArticle(article) : undefined}
          />
        );
      })}
    </View>
  );
}

type RowProps = {
  article:         ArticleSource;
  isFirstReported: boolean;
  isLast:          boolean;
  railColor:       string;
  onPress?:        () => void;
};

function TimelineRow({ article, isFirstReported, isLast, railColor, onPress }: RowProps) {
  const { palette } = useTheme();

  const when = article.published_at ? formatRelativeTime(article.published_at) : "";
  const sourceLabel = (article.source_display_name ?? article.source).toUpperCase();

  return (
    <View style={styles.row}>
      {/* left gutter: rail + dot */}
      <View style={styles.gutter}>
        <View
          style={[
            styles.rail,
            {
              backgroundColor: railColor,
              top:             0,
              bottom:          isLast ? "50%" : 0,
              left:            RAIL_INSET,
            },
          ]}
        />
        <View
          style={[
            styles.dot,
            {
              backgroundColor: railColor,
              borderColor:     palette.bg,
              top:             CARD_TOP_OFFSET,
              left:            RAIL_INSET + RAIL_WIDTH / 2 - DOT_SIZE / 2,
            },
          ]}
        />
      </View>

      {/* source card */}
      <Pressable
        onPress={onPress}
        accessibilityRole="link"
        accessibilityLabel={`${sourceLabel}${isFirstReported ? ", first reported" : ""}${when ? `, ${when}` : ""}. ${article.title}. Read on ${article.source_display_name ?? article.source.replace(/_/g, " ")}`}
        style={({ pressed }) => [
          styles.card,
          {
            backgroundColor: palette.cardBgSoft,
            borderColor:     palette.border,
            borderRadius:    radius.card,
            opacity:         pressed ? 0.85 : 1,
          },
        ]}
      >
        <View style={styles.cardHeader}>
          <SectionLabel style={{ color: palette.accent }}>{sourceLabel}</SectionLabel>
          {isFirstReported && (
            <SectionLabel muted style={styles.firstReported}>FIRST REPORTED</SectionLabel>
          )}
        </View>

        {when && (
          <Meta muted style={{ marginTop: space.xs }}>{when}</Meta>
        )}

        <Headline numberOfLines={3} style={[styles.cardTitle, { fontSize: 16, lineHeight: 22 }]}>
          {article.title}
        </Headline>

        {article.author && (
          <Meta muted style={{ marginTop: space.xs }}>
            By {article.author}
          </Meta>
        )}

        <Body
          accessibilityRole="link"
          style={[
            styles.readLink,
            {
              color:              palette.accent,
              fontFamily:         fonts.sansSemibold,
              textDecorationLine: "underline",
            },
          ]}
        >
          Read on {article.source_display_name ?? article.source.replace(/_/g, " ")} →
        </Body>
      </Pressable>
    </View>
  );
}

const GUTTER_WIDTH = 28;

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    marginBottom:  space.lg,
  },
  gutter: {
    width:    GUTTER_WIDTH,
    position: "relative",
  },
  rail: {
    position: "absolute",
    width:    RAIL_WIDTH,
  },
  dot: {
    position:     "absolute",
    width:        DOT_SIZE,
    height:       DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
    borderWidth:  2,
  },
  card: {
    flex:        1,
    padding:     space.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems:    "center",
    gap:           space.sm,
  },
  firstReported: {
    fontSize: 10,
    letterSpacing: 1,
  },
  cardTitle: {
    marginTop: space.sm,
  },
  readLink: {
    ...textTokens.preview,
    marginTop: space.sm,
  },
});
