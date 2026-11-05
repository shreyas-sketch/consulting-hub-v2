// The app's React Query client and its defaults, in one place.
import { QueryClient } from "@tanstack/react-query";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        refetchOnWindowFocus: false,
        // 4xx answers (401/402/403/404) will not change on retry; network blips get one more try.
        retry: (count, err) => {
          const s = err?.response?.status;
          if (s && s >= 400 && s < 500) return false;
          return count < 1;
        },
      },
      // Writes are never retried by the client library: the API decides (an AI-busy POST is retried once in
      // lib/api.js, after the server has given the use back).
      mutations: { retry: false },
    },
  });
}
