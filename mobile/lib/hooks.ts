/**
 * lib/hooks.ts — React Query hooks for every endpoint in lib/api.ts.
 *
 * Hooks are thin: queryKey + queryFn + sensible defaults (5-min stale time,
 * refetch on focus). Components consume `useTopStories()`, `useStoryDetail(id)`,
 * etc. and never touch the underlying fetch.
 *
 * AsyncStorage persister is wired in app/_layout.tsx, so query results are
 * cached on-device and survive app restarts — that's the offline story
 * for Phase F.
 */
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

import { api, type StoryDetail, type StoryListResponse, type Topic, type TopicFeedResponse } from "./api";

const FIVE_MINUTES_MS = 5 * 60 * 1_000;
const ONE_HOUR_MS     = 60 * 60 * 1_000;

// ---------------------------------------------------------------------------
// Query keys (centralised so cache invalidation later is straightforward)
// ---------------------------------------------------------------------------

export const qk = {
  topStories: (params: { hours?: number; limit?: number; offset?: number } = {}) =>
    ["stories", "top", params] as const,
  allStories: (params: { hours?: number; limit?: number; offset?: number } = {}) =>
    ["stories", "all", params] as const,
  storyDetail: (storyId: number) =>
    ["stories", "detail", storyId] as const,
  topicFeed: (topic: Topic, params: { hours?: number; multi_limit?: number; singletons_n?: number } = {}) =>
    ["feed", "topic", topic, params] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useTopStories(
  params: { hours?: number; limit?: number; offset?: number } = {},
  options?: Partial<UseQueryOptions<StoryListResponse>>,
) {
  return useQuery<StoryListResponse>({
    queryKey: qk.topStories(params),
    queryFn:  ({ signal }) => api.topStories(params, signal),
    staleTime: FIVE_MINUTES_MS,
    gcTime:    ONE_HOUR_MS,
    ...options,
  });
}

export function useAllStories(
  params: { hours?: number; limit?: number; offset?: number } = {},
  options?: Partial<UseQueryOptions<StoryListResponse>>,
) {
  return useQuery<StoryListResponse>({
    queryKey: qk.allStories(params),
    queryFn:  ({ signal }) => api.allStories(params, signal),
    staleTime: FIVE_MINUTES_MS,
    gcTime:    ONE_HOUR_MS,
    ...options,
  });
}

export function useStoryDetail(
  storyId: number,
  options?: Partial<UseQueryOptions<StoryDetail>>,
) {
  return useQuery<StoryDetail>({
    queryKey: qk.storyDetail(storyId),
    queryFn:  ({ signal }) => api.storyDetail(storyId, signal),
    enabled:  Number.isFinite(storyId) && storyId > 0,
    staleTime: FIVE_MINUTES_MS,
    gcTime:    ONE_HOUR_MS,
    ...options,
  });
}

export function useTopicFeed(
  topic: Topic,
  params: { hours?: number; multi_limit?: number; singletons_n?: number } = {},
  options?: Partial<UseQueryOptions<TopicFeedResponse>>,
) {
  return useQuery<TopicFeedResponse>({
    queryKey: qk.topicFeed(topic, params),
    queryFn:  ({ signal }) => api.topicFeed(topic, params, signal),
    staleTime: FIVE_MINUTES_MS,
    gcTime:    ONE_HOUR_MS,
    ...options,
  });
}
