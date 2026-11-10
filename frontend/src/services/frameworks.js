// Frameworks domain: "Work along with Akshat", the three frameworks from the live workshop as hands-on cases.
// Mirrors backend/features/frameworks.py. Saving is free; a proposal counts one `fw_proposal`.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { qk } from "./queryKeys";

export const frameworksApi = {
  list: async () => (await api.get("/frameworks")).data,
  get: async (key) => (await api.get(`/frameworks/${key}`)).data,
  save: async (key, answers) => (await api.put(`/frameworks/${key}/response`, answers)).data,
  proposal: async (key) => (await api.post(`/frameworks/${key}/proposal`, {})).data,
};

export const useFrameworks = () => useQuery({ queryKey: qk.frameworks.all, queryFn: frameworksApi.list });
export const useFramework = (key) => useQuery({ queryKey: qk.frameworks.detail(key), queryFn: () => frameworksApi.get(key), enabled: !!key });

// Saving or generating changes the framework itself and the list (saved / proposal chips).
function useFrameworkWrite(key, fn, { onDone } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(qk.frameworks.detail(key), data);
      qc.invalidateQueries({ queryKey: qk.frameworks.all });
      onDone?.(data);
    },
  });
}
export const useSaveFramework = (key, opts) => useFrameworkWrite(key, (answers) => frameworksApi.save(key, answers), opts);
export const useFrameworkProposal = (key, opts) => useFrameworkWrite(key, () => frameworksApi.proposal(key), opts);
