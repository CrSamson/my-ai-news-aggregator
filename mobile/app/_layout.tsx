/**
 * app/_layout.tsx — root Expo Router layout.
 *
 * Responsibilities:
 *   1. Load custom fonts (Lora serif + Inter sans) before rendering anything
 *   2. Install React Query provider with AsyncStorage persister so query
 *      results survive app restarts (offline support, Phase F)
 *   3. Render the (tabs) stack
 *
 * The splash screen stays up until fonts have loaded so the first
 * paint doesn't flash system-default fonts.
 */
import { Lora_500Medium, Lora_700Bold } from "@expo-google-fonts/lora";
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
} from "@expo-google-fonts/inter";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import "react-native-reanimated";

import { useTheme } from "../lib/useTheme";

export { ErrorBoundary } from "expo-router";

export const unstable_settings = {
  initialRouteName: "(tabs)",
};

SplashScreen.preventAutoHideAsync();

// ---------------------------------------------------------------------------
// React Query setup
// ---------------------------------------------------------------------------

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 5-min stale time matches what we tell each useQuery hook; keep here
      // as a safety net for queries that forget to set their own.
      staleTime: 5 * 60 * 1_000,
      retry: 1,
      // Keep cached data for an hour so a quick app close/reopen doesn't
      // re-fetch every screen.
      gcTime: 60 * 60 * 1_000,
    },
  },
});

const persister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key:     "brevio-rq-cache",
  // Don't persist more than 7 days of stale data.
  throttleTime: 1_000,
});

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export default function RootLayout() {
  const [loaded, error] = useFonts({
    Lora_500Medium,
    Lora_700Bold,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
  });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) {
      SplashScreen.hideAsync();
    }
  }, [loaded]);

  if (!loaded) return null;

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{ persister, maxAge: 7 * 24 * 60 * 60 * 1_000 }}
    >
      <RootLayoutNav />
    </PersistQueryClientProvider>
  );
}

function RootLayoutNav() {
  const { scheme, palette } = useTheme();
  return (
    <>
      <StatusBar style={scheme === "dark" ? "light" : "dark"} />
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="story/[id]"
          options={{
            headerShown:     true,
            headerTitle:     "",
            headerBackTitle: "Back",
            headerStyle:     { backgroundColor: palette.bg },
            headerShadowVisible: false,
            headerTintColor: palette.accent,
          }}
        />
        <Stack.Screen
          name="browser"
          options={{
            presentation: "modal",
            headerShown:  false,
          }}
        />
      </Stack>
    </>
  );
}
