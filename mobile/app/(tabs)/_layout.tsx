/**
 * app/(tabs)/_layout.tsx — bottom-tabs navigation.
 *
 * Four tabs per UI spec §2:
 *   Top      — multi-source stories first (the headline view)
 *   Topics   — filtered by topic
 *   All      — chronological feed of everything
 *   About    — what Brevio is + links
 *
 * Tab bar styling honours the calm aesthetic: peach for active, muted for
 * inactive, no shadows, thin top border separating from content.
 */
import React from "react";
import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router";

import { fonts } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

function TabIcon({ name, color }: { name: IconName; color: string }) {
  return <Ionicons name={name} size={22} color={color} />;
}

export default function TabsLayout() {
  const { palette } = useTheme();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor:   palette.accent,
        tabBarInactiveTintColor: palette.textMuted,
        tabBarStyle: {
          backgroundColor: palette.cardBg,
          borderTopColor:  palette.border,
        },
        tabBarLabelStyle: {
          fontFamily: fonts.sansMedium,
          fontSize:   11,
          letterSpacing: 0.2,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Top",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? "newspaper" : "newspaper-outline"} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="topics"
        options={{
          title: "Topics",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? "bookmarks" : "bookmarks-outline"} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="all"
        options={{
          title: "All",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? "list-circle" : "list-circle-outline"} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="about"
        options={{
          title: "About",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? "information-circle" : "information-circle-outline"} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
