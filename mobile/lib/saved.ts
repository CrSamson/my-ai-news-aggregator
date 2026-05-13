/**
 * lib/saved.ts — AsyncStorage-backed bookmark store + React hook.
 *
 * Stores a Set of story IDs the user has tapped to save. Persists across
 * launches (same AsyncStorage instance the React Query cache uses).
 *
 * Why a Set, not a list of full story objects:
 *   - Story data is already in the React Query cache. Keyed by ID, we
 *     can re-fetch a saved story's detail on demand without duplicating
 *     payloads in two places.
 *   - The persisted blob stays tiny (10 chars per ID instead of ~500
 *     bytes per StoryCard).
 *
 * The hook subscribes to in-process changes via a module-level event
 * emitter, so toggling a bookmark on one screen updates the indicator
 * everywhere else instantly — without a full app-state library.
 */
import { useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "brevio.saved_story_ids.v1";

// In-memory cache + subscribers. The persisted blob is loaded once on
// first read; subsequent reads stay sync.
let memo: Set<number> | null = null;
let loadPromise: Promise<Set<number>> | null = null;

const listeners = new Set<() => void>();
function notify() {
  listeners.forEach((l) => l());
}

async function load(): Promise<Set<number>> {
  if (memo) return memo;
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        const arr = JSON.parse(raw) as unknown;
        if (Array.isArray(arr)) {
          memo = new Set(arr.filter((n) => typeof n === "number"));
          return memo;
        }
      }
    } catch {
      // Storage hiccup — degrade to empty set rather than blocking the UI.
    }
    memo = new Set<number>();
    return memo;
  })();
  return loadPromise;
}

async function persist(): Promise<void> {
  if (!memo) return;
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify([...memo]));
  } catch {
    // Worst case the bookmark doesn't survive a relaunch — non-fatal.
  }
}

export async function toggleSaved(storyId: number): Promise<boolean> {
  const set = await load();
  let saved: boolean;
  if (set.has(storyId)) {
    set.delete(storyId);
    saved = false;
  } else {
    set.add(storyId);
    saved = true;
  }
  await persist();
  notify();
  return saved;
}

export async function clearAllSaved(): Promise<void> {
  const set = await load();
  set.clear();
  await persist();
  notify();
}

/**
 * Subscribe to bookmark changes. Returns a snapshot Set on first render
 * and stays in sync via the module-level listener.
 */
export function useSavedStories(): {
  ids:     ReadonlySet<number>;
  isSaved: (id: number) => boolean;
  count:   number;
  ready:   boolean;
} {
  const [snapshot, setSnapshot] = useState<Set<number>>(memo ?? new Set());
  const [ready, setReady]       = useState<boolean>(memo !== null);

  useEffect(() => {
    let cancelled = false;
    if (!memo) {
      load().then((set) => {
        if (cancelled) return;
        setSnapshot(new Set(set));
        setReady(true);
      });
    }
    const listener = () => {
      if (memo) setSnapshot(new Set(memo));
    };
    listeners.add(listener);
    return () => {
      cancelled = true;
      listeners.delete(listener);
    };
  }, []);

  return {
    ids:     snapshot,
    isSaved: (id) => snapshot.has(id),
    count:   snapshot.size,
    ready,
  };
}
