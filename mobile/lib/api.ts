/**
 * lib/api.ts — typed HTTP client for the Brevio Modal API.
 *
 * Single fetch wrapper, no third-party HTTP client needed at this scale.
 * Base URL comes from EXPO_PUBLIC_API_URL (settable in .env, falls back to
 * the live Modal URL so the app works out of the box without env config).
 *
 * Type definitions mirror api/schemas.py from the Python backend; keep
 * them in sync manually until we wire up an OpenAPI codegen step.
 */

const DEFAULT_BASE_URL = "https://crsamson--brevio-api-fastapi-app.modal.run";

export const API_BASE_URL: string =
  (process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");

// ---------------------------------------------------------------------------
// Response types — mirror api/schemas.py
// ---------------------------------------------------------------------------

export type Health = {
  ok:      boolean;
  version: string;
};

export type StoryCard = {
  id:              number;
  is_multi_source: boolean;
  headline:        string;
  summary_preview: string;
  topics:          string[];
  article_count:   number;
  source_ids:      string[];
  primary_source:  string | null;
  first_seen_at:   string | null;     // ISO 8601 (parse with new Date())
  last_seen_at:    string | null;
};

export type ArticleSource = {
  id:                  number;
  source:              string;
  source_display_name: string | null;
  url:                 string;
  title:               string;
  author:              string | null;
  published_at:        string | null;
  rss_summary:         string | null;
};

export type StoryDetail = StoryCard & {
  summary:    string;
  key_points: string[];
  entities:   string[];
  articles:   ArticleSource[];
};

export type StoryListResponse = {
  items:           StoryCard[];
  next_offset:     number | null;
  total_in_window: number | null;
};

export type TopicFeedResponse = {
  topic:          string;
  multi_stories:  StoryCard[];
  top_singletons: StoryCard[];
};

export type Topic = "ai" | "technology" | "business" | "science" | "general";

export const TOPICS: readonly Topic[] = ["ai", "technology", "business", "science", "general"] as const;

// ---------------------------------------------------------------------------
// HTTP error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public status:  number,
    public detail:  string,
    public url:     string,
  ) {
    super(`Brevio API ${status} ${url}: ${detail}`);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Core fetch
// ---------------------------------------------------------------------------

type QueryParams = Record<string, string | number | boolean | undefined>;

function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined) continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function get<T>(path: string, params?: QueryParams, signal?: AbortSignal): Promise<T> {
  const url = buildUrl(path, params);
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // body wasn't JSON; keep status text
    }
    throw new ApiError(res.status, detail, url);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------

export const api = {
  health: (signal?: AbortSignal) =>
    get<Health>("/api/v1/health", undefined, signal),

  topStories: (
    params: { limit?: number; offset?: number; hours?: number } = {},
    signal?: AbortSignal,
  ) =>
    get<StoryListResponse>(
      "/api/v1/stories/top",
      { limit: params.limit, offset: params.offset, hours: params.hours },
      signal,
    ),

  allStories: (
    params: { limit?: number; offset?: number; hours?: number } = {},
    signal?: AbortSignal,
  ) =>
    get<StoryListResponse>(
      "/api/v1/stories/all",
      { limit: params.limit, offset: params.offset, hours: params.hours },
      signal,
    ),

  storyDetail: (storyId: number, signal?: AbortSignal) =>
    get<StoryDetail>(`/api/v1/stories/${storyId}`, undefined, signal),

  topicFeed: (
    topic: Topic,
    params: { multi_limit?: number; singletons_n?: number; hours?: number } = {},
    signal?: AbortSignal,
  ) =>
    get<TopicFeedResponse>(
      `/api/v1/feed/topic/${topic}`,
      { multi_limit: params.multi_limit, singletons_n: params.singletons_n, hours: params.hours },
      signal,
    ),
};
