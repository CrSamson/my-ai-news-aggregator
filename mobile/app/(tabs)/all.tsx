/**
 * app/(tabs)/all.tsx — All News tab.
 *
 * Phase B scope: count display + first 5 headlines as plain text.
 * Full chronological feed UI ships in Phase D.
 */
import React from "react";
import { View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Body, Card, DisplayHL, Headline, Meta } from "../../components/ui";
import { useAllStories } from "../../lib/hooks";
import { formatRelativeTime } from "../../lib/time";
import { space } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

export default function AllNewsTab() {
  const { palette } = useTheme();
  const { data, isLoading } = useAllStories({ hours: 48, limit: 10 });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={["top"]}>
      <View style={{ padding: space.xl }}>
        <DisplayHL>All News</DisplayHL>
        <Meta muted style={{ marginTop: space.xs }}>
          Last 48 hours
        </Meta>

        <View style={{ marginTop: space.xl }}>
          {isLoading ? (
            <Card static>
              <Body muted>Loading…</Body>
            </Card>
          ) : (
            <Card static>
              <Body muted>
                {data?.items.length ?? 0} of {data?.total_in_window ?? 0} stories in the
                last 48h.
              </Body>
              <Meta muted style={{ marginTop: space.sm }}>
                Full feed UI lands in Phase D — for now showing the first few headlines:
              </Meta>
              {data?.items.slice(0, 5).map((s) => (
                <View key={s.id} style={{ marginTop: space.md }}>
                  <Headline numberOfLines={2}>{s.headline}</Headline>
                  <Meta muted style={{ marginTop: 2 }}>
                    {s.primary_source ?? "?"} · {formatRelativeTime(s.last_seen_at)}
                  </Meta>
                </View>
              ))}
            </Card>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}
