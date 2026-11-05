// Cases domain: the HTTP calls and the React Query hooks screens use. Screens never build URLs or keys themselves;
// a change to the endpoint or to what a write must refresh is made here once.
//
// Mirrors backend/features/cases/ (router → service → repository).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { qk } from "./queryKeys";

// ---- HTTP ------------------------------------------------------------------------------------------------------
export const casesApi = {
  list: async () => (await api.get("/cases")).data,
  // The case screen shows its own lock card, so the global upgrade sheet stays closed for this read.
  get: async (id) => (await api.get(`/cases/${id}`, { _silentGate: true })).data,
  answer: async (id, answer) => (await api.post(`/cases/${id}/answer`, { answer })).data,
};

// ---- hooks -----------------------------------------------------------------------------------------------------
export const useCases = () => useQuery({ queryKey: qk.cases.all, queryFn: casesApi.list });

export const useCase = (id) => useQuery({ queryKey: qk.cases.detail(id), queryFn: () => casesApi.get(id), enabled: !!id });

// Sending an answer changes the case (your score, the model answer), the list (your score chip) and My Consulting
// File. `onDone` runs after the case itself has refreshed (e.g. refreshMe() so usage limits update).
export function useAnswerCase(id, { onDone } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (answer) => casesApi.answer(id, answer),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.cases.detail(id) });
      qc.invalidateQueries({ queryKey: qk.cases.all });
      qc.invalidateQueries({ queryKey: qk.file });
      onDone?.();
    },
  });
}
