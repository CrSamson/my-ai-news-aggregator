/**
 * components/StoryCard/SavedIndicator.tsx — small bookmark badge.
 *
 * Renders a peach bookmark icon in the top-right corner of a story card
 * when the user has saved it. Hidden otherwise. Subscribes to the saved-
 * stories store so it stays in sync as the user toggles bookmarks
 * elsewhere (Story Detail header, Saved screen).
 */
import React from "react";
import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { useSavedStories } from "../../lib/saved";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type Props = { storyId: number };

export function SavedIndicator({ storyId }: Props) {
  const { palette } = useTheme();
  const { isSaved } = useSavedStories();

  if (!isSaved(storyId)) return null;

  return (
    <View style={styles.wrap} pointerEvents="none">
      <Ionicons name="bookmark" size={14} color={palette.accent} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    top:      space.sm,
    right:    space.sm,
  },
});
