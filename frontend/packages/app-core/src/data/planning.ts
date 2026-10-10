import type { components } from "@kainem/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useServices } from "../context";
import { validTimezone } from "./format";

export type Task = components["schemas"]["TaskOut"];
export type EventsPage = components["schemas"]["EventsOut"];

// The user forwards a message in Telegram and comes straight back: always refetch on return,
// even if the data is younger than the default stale time.
const REFETCH_ON_RETURN = { refetchOnWindowFocus: "always" as const };

export const planningKeys = {
  tasks: (familyId: string) => ["families", familyId, "tasks"] as const,
  events: (familyId: string) => ["families", familyId, "events"] as const,
};

async function unwrap<T>(p: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await p;
  if (data === undefined) throw error ?? new Error("request failed");
  return data;
}

export function useOpenTasks(familyId: string) {
  const { api } = useServices();
  return useQuery({
    ...REFETCH_ON_RETURN,
    queryKey: planningKeys.tasks(familyId),
    enabled: Boolean(familyId),
    refetchOnMount: "always",
    queryFn: ({ signal }) => unwrap(api.GET("/v1/families/{family_id}/tasks", { signal, params: { path: { family_id: familyId } } })),
  });
}

export function useUpcomingEvents(familyId: string) {
  const { api } = useServices();
  return useQuery({
    ...REFETCH_ON_RETURN,
    queryKey: planningKeys.events(familyId),
    enabled: Boolean(familyId),
    refetchOnMount: "always",
    queryFn: ({ signal }) =>
      unwrap(api.GET("/v1/families/{family_id}/events", { signal, params: { path: { family_id: familyId } } })),
  });
}

export function eventsTimezone(page: EventsPage | undefined): string {
  return validTimezone(page?.timezone);
}

/** Confirm with the server before showing Completed. No offline mutation queue. */
export function useSetTaskDone(familyId: string) {
  const { api } = useServices();
  const qc = useQueryClient();
  const key = planningKeys.tasks(familyId);
  const currentFamily = useRef(familyId);
  currentFamily.current = familyId;
  const pending = useRef(new Set<string>());
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const mounted = useRef(true);
  const [result, setResult] = useState<{ family: string; rows: Record<string, "Saving" | "Completed" | "Error">; completed: boolean }>({ family: familyId, rows: {}, completed: false });
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; timers.current.forEach(clearTimeout); timers.current.clear(); };
  }, []);
  function setRow(id: string, status: "Saving" | "Completed" | "Error") {
    if (!mounted.current || currentFamily.current !== familyId) return;
    setResult(previous => ({ family: familyId, rows: { ...(previous.family === familyId ? previous.rows : {}), [id]: status }, completed: status === "Completed" || (previous.family === familyId && previous.completed) }));
  }
  const mutation = useMutation({
    networkMode: "always",
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      unwrap(
        api.PATCH("/v1/families/{family_id}/tasks/{task_id}", {
          params: { path: { family_id: familyId, task_id: id } },
          body: { done },
        }),
      ),
    onMutate: async ({ id }) => {
      if (!navigator.onLine) throw new Error("offline");
      setRow(id, "Saving");
      await qc.cancelQueries({ queryKey: key });
    },
    onSuccess: (task, { id }) => {
      // A late write response must not repopulate a cleared cache after sign-out.
      if (!mounted.current || currentFamily.current !== familyId) return;
      setRow(id, "Completed");
      qc.setQueryData<Task[]>(key, tasks => tasks?.map(t => t.id === id ? task : t));
      const timer = setTimeout(() => {
        timers.current.delete(timer);
        if (!mounted.current || currentFamily.current !== familyId) return;
        qc.setQueryData<Task[]>(key, tasks => tasks?.filter(t => t.id !== id));
        if (currentFamily.current === familyId) setResult(previous => {
          if (previous.family !== familyId) return previous;
          const rows = { ...previous.rows }; delete rows[id];
          return { ...previous, rows };
        });
        void qc.invalidateQueries({ queryKey: key });
      }, 650);
      timers.current.add(timer);
    },
    onError: (_err, { id }) => setRow(id, "Error"),
    onSettled: (_data, _error, { id }) => { pending.current.delete(`${familyId}:${id}`); },
  });
  return {
    rows: result.family === familyId ? result.rows : {},
    hasCompleted: result.family === familyId && result.completed,
    mutate(variables: { id: string; done: boolean }) {
      const identity = `${familyId}:${variables.id}`;
      if (!navigator.onLine || pending.current.has(identity)) return;
      pending.current.add(identity);
      mutation.mutate(variables);
    },
  };
}
