/**
 * components/StoryCard/StoryCard.tsx — variant dispatcher.
 *
 * Picks <MultiStoryCard> vs <SingletonCard> based on `is_multi_source`.
 * Lists (TopStoriesTab, AllNewsTab, TopicsTab) render <StoryCard> and
 * never have to branch.
 */
import React from "react";

import { MultiStoryCard } from "./MultiStoryCard";
import { SingletonCard } from "./SingletonCard";
import type { StoryCard as StoryCardData } from "../../lib/api";

type Props = {
  story:    StoryCardData;
  onPress?: () => void;
  style?:   any;
};

export function StoryCard({ story, onPress, style }: Props) {
  if (story.is_multi_source) {
    return <MultiStoryCard story={story} onPress={onPress} style={style} />;
  }
  return <SingletonCard story={story} onPress={onPress} style={style} />;
}
