/**
 * lib/registerSW.ts — registers the PWA service worker on web only.
 *
 * Imported for its side-effect from app/_layout.tsx. On native (iOS/Android)
 * this entire module is a no-op because Platform.OS !== "web" short-circuits
 * before we touch `navigator`.
 *
 * The dev server (expo start --web) doesn't ship the SW at /sw.js — the file
 * lives under mobile/public/ and only appears in the production build output
 * at mobile/dist/sw.js. We gate registration on __DEV__ so local dev doesn't
 * 404-log every reload.
 */
import { Platform } from "react-native";

declare const __DEV__: boolean;

if (Platform.OS === "web" && !__DEV__) {
  // Defer to the load event so SW registration doesn't compete with the
  // first paint. The user can interact with the app before the SW is live.
  if (typeof window !== "undefined" && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        // Non-fatal — the app works without the SW, just no offline cache.
        // eslint-disable-next-line no-console
        console.warn("[brevio] SW registration failed:", err);
      });
    });
  }
}

export {};
