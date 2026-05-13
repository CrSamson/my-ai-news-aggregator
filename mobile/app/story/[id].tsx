/**
 * app/story/[id].tsx — Instagram-Stories-style story pager.
 *
 * Phase G: tapping a card on the Top tab opens this screen with two route
 * params:
 *   - id     — which story to start on
 *   - queue  — comma-separated story IDs from the originating feed
 *
 * The screen renders all queued stories side-by-side inside a horizontal
 * ScrollView with `pagingEnabled`, so swiping left/right snaps to the next
 * or previous story. Progress bars at the top mirror Instagram Stories: one
 * dot per item in the queue, current one peach-filled.
 *
 * Tap zones overlay the left and right thirds of the screen — tap-right
 * advances, tap-left goes back — so the screen works one-handed without
 * fighting the swipe gesture.
 *
 * Direct link (no `queue` param): falls back to a single-story render. This
 * is what an external share link or a refresh on a deep URL hits.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";

import { StoryView } from "../../components/story/StoryView";
import { StoryPagerHeader } from "../../components/story/StoryPagerHeader";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

function parseQueue(raw: string | string[] | undefined): number[] {
  if (!raw) return [];
  const str = Array.isArray(raw) ? raw[0] : raw;
  return str
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
}

export default function StoryDetailScreen() {
  const { palette } = useTheme();
  const router      = useRouter();
  const { width }   = useWindowDimensions();
  const params      = useLocalSearchParams<{ id: string; queue?: string }>();

  const currentId = Number(params.id);
  const queue     = useMemo(() => parseQueue(params.queue), [params.queue]);
  const pages     = queue.length > 0 ? queue : [currentId];

  const startIndex = useMemo(() => {
    const i = pages.indexOf(currentId);
    return i >= 0 ? i : 0;
  }, [pages, currentId]);

  const [activeIndex, setActiveIndex] = useState(startIndex);
  const scrollRef = useRef<ScrollView>(null);

  // Jump to the starting page on mount (and whenever width recomputes, e.g.
  // on rotation — keep the user pinned to the current story).
  useEffect(() => {
    scrollRef.current?.scrollTo({ x: startIndex * width, y: 0, animated: false });
  }, [startIndex, width]);

  const goToIndex = (i: number) => {
    const clamped = Math.max(0, Math.min(pages.length - 1, i));
    scrollRef.current?.scrollTo({ x: clamped * width, y: 0, animated: true });
    setActiveIndex(clamped);
  };

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const i = Math.round(e.nativeEvent.contentOffset.x / width);
    if (i !== activeIndex) {
      setActiveIndex(i);
      // Reflect the active story in the URL so a refresh / share lands on it.
      const newId = pages[i];
      if (newId && newId !== currentId) {
        router.setParams({ id: String(newId) });
      }
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["bottom"]}>
      <StoryPagerHeader
        total={pages.length}
        currentIndex={activeIndex}
        onJump={goToIndex}
      />

      <View style={{ flex: 1 }}>
        <ScrollView
          ref={scrollRef}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          onMomentumScrollEnd={onScrollEnd}
          // On web, onMomentumScrollEnd doesn't fire — use onScrollEnd alternative.
          onScrollEndDrag={onScrollEnd}
          // Snap precisely to each page even when scroll velocity is low.
          decelerationRate="fast"
          snapToInterval={width}
          snapToAlignment="start"
        >
          {pages.map((id) => (
            <StoryView key={id} storyId={id} width={width} />
          ))}
        </ScrollView>

        {/* Tap zones: thin vertical strips on the screen edges. Confined to
            the outer 12% on each side so the middle 76% stays free for the
            ScrollView's own scrolling + link taps lower on the page. Also
            cap height so they don't overlap the source-card region near the
            bottom — only the upper portion of each edge is a "tap to advance"
            affordance. */}
        {pages.length > 1 && (
          <>
            <Pressable
              accessibilityLabel="Previous story"
              accessibilityRole="button"
              onPress={() => goToIndex(activeIndex - 1)}
              style={[styles.tapZone, { left: 0, width: width * 0.12 }]}
            />
            <Pressable
              accessibilityLabel="Next story"
              accessibilityRole="button"
              onPress={() => goToIndex(activeIndex + 1)}
              style={[styles.tapZone, { right: 0, width: width * 0.12 }]}
            />
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  tapZone: {
    position: "absolute",
    top:      0,
    // Confine to the very top of the screen so it doesn't fight links lower
    // down. Touching the top corners is the "tap to advance" affordance.
    height:   100,
  },
});
