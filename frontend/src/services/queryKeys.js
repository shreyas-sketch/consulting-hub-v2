// One factory for every React Query key, so a write knows exactly which reads to refresh and keys never drift
// apart between screens ("cases" vs "case-list"). Keys are arrays: broader keys are prefixes of narrower ones, so
// `invalidateQueries({ queryKey: qk.cases.all })` also refreshes every single case.
//
// Add a domain here when you give it a service module in src/services/.
export const qk = {
  me: ["me"],
  home: ["me-home"],
  file: ["file"],
  cases: {
    all: ["cases"],
    detail: (id) => ["case", id],
  },
  frameworks: {
    all: ["frameworks"],
    detail: (key) => ["framework", key],
  },
};
