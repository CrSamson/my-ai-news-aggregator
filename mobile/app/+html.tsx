/**
 * app/+html.tsx — Expo Router static-rendering HTML wrapper.
 *
 * Expo SDK 54 does NOT inject web-manifest / theme-color / apple-touch
 * meta tags from app.json's `web` block at static-export time. This file
 * is the documented escape hatch (https://docs.expo.dev/router/reference/static-rendering/#root-html).
 *
 * Notable elements here, in plain English:
 *   - <link rel="manifest"> points the browser at /manifest.webmanifest
 *     (public/manifest.webmanifest, copied verbatim to dist/). Without
 *     this, Chrome's PWA install prompt never fires.
 *   - <meta name="theme-color"> tints the iOS / Android status bar to
 *     match our peach accent when the app is opened from the home screen.
 *   - apple-mobile-web-app-* meta tags are iOS Safari's pre-manifest API
 *     for "Add to Home Screen" — needed because iOS only partially honors
 *     web-manifest fields even in 2026.
 *   - <ScrollViewStyleReset /> is Expo Router's required reset that makes
 *     ScrollView behave on web; do not remove.
 */
import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"
        />

        <title>Brevio</title>
        <meta name="description" content="One story, every source, full timeline." />

        {/* PWA install + theming */}
        <link rel="manifest" href="/manifest.webmanifest" />
        <meta name="theme-color" content="#EE9970" />
        <meta name="color-scheme" content="light dark" />

        {/* iOS Safari "Add to Home Screen" */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-title" content="Brevio" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <link rel="apple-touch-icon" href="/favicon.ico" />

        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  );
}
