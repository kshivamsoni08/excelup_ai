"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Invalidate everything after a mutation so all dashboards update live. */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

type Extra = {
  onSuccess?: (data: any, vars: any, ctx: any) => void;
  onError?: (err: unknown, vars: any, ctx: any) => void;
};

/** Mutation wrapper that invalidates all queries on success (real-time feel). */
export function useLiveMutation(mutationFn: (vars: any) => Promise<any>, extra: Extra = {}) {
  const refreshAll = useRefreshAll();
  return useMutation({
    mutationFn,
    onSuccess: (data: any, vars: any, ctx: any) => {
      refreshAll();
      extra.onSuccess?.(data, vars, ctx);
    },
    onError: (err: unknown, vars: any, ctx: any) => {
      extra.onError?.(err, vars, ctx);
    },
  });
}

export function useLiveApi() {
  const refreshAll = useRefreshAll();
  return (path: string, options?: { method?: string; body?: unknown; formData?: FormData }) =>
    api(path, options).then((r) => {
      refreshAll();
      return r;
    });
}
