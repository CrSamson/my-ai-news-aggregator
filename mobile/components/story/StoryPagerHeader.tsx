/**
 * components/story/StoryPagerHeader.tsx — Instagram-Stories-style progress bars.
 *
 * Renders one short horizontal segment per story in the queue. The currently-
 * viewed segment is solid peach; segments the user has already swiped past
 * are also solid (so the bar reads as "you're N of M deep into your feed");
 * upcoming segments are dim. Tapping a segment jumps to that story.
 *
 * News content isn't time-paced (we don't auto-advance), so segments don't
 * animate-fill the way Instagram's do — they're a position indicator,
 * not a timer.
 */
import React from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type Props = {
  total:          number;
  currentIndex:   number;
  onJump?:        (index: number) => void;
};

export function StoryPagerHeader({ total, currentIndex, onJump }: Props) {
  const { palette } = useTheme();

  if (total <= 1) return null;

  return (
    <View style={[styles.row, { paddingHorizontal: space.lg }]}>
      {Array.from({ length: total }, (_, i) => {
        const isPast    = i < currentIndex;
        const isCurrent = i === currentIndex;
        const fillColor = isPast || isCurrent ? palette.accent : palette.accent + "33";  // 33 = 20% alpha

        return (
          <Pressable
            key={i}
            onPress={onJump ? () => onJump(i) : undefined}
            accessibilityRole="button"
            accessibilityLabel={`Story ${i + 1} of ${total}`}
            accessibilityState={{ selected: isCurrent }}
            style={({ pressed }) => [
              styles.segmentTouch,
              pressed && { opacity: 0.6 },
            ]}
          >
            <View style={[styles.segment, { backgroundColor: fillColor }]} />
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection:  "row",
    alignItems:     "center",
    gap:            4,
    paddingVertical: space.sm,
  },
  segmentTouch: {
    flex:            1,
    paddingVertical: 6,   // Wider hit zone than the visible bar.
  },
  segment: {
    height:       2,
    borderRadius: 1,
  },
});
