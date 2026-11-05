// My Consulting File: everything the member has made, on one page. Many tools refresh it after a write
// (invalidate `qk.file`).
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { qk } from "./queryKeys";

export const fileApi = {
  get: async () => (await api.get("/file")).data,
  markViewed: () => api.post("/file/viewed"),
};

export const useConsultingFile = () => useQuery({ queryKey: qk.file, queryFn: fileApi.get });
