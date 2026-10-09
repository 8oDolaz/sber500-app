import type { components } from "@kainem/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServices } from "../context";

export type Task = components["schemas"]["TaskOut"];
export type EventsPage = components["schemas"]["EventsOut"];

const DEFAULT_TZ = "Europe/Moscow";

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
    queryFn: () => unwrap(api.GET("/v1/families/{family_id}/tasks", { params: { path: { family_id: familyId } } })),
  });
}

export function useUpcomingEvents(familyId: string) {
  const { api } = useServices();
  return useQuery({
    ...REFETCH_ON_RETURN,
    queryKey: planningKeys.events(familyId),
    queryFn: () =>
      unwrap(api.GET("/v1/families/{family_id}/events", { params: { path: { family_id: familyId } } })),
  });
}

export function eventsTimezone(page: EventsPage | undefined): string {
  return page?.timezone ?? DEFAULT_TZ;
}

/** Tap on the list dot. Optimistic: the row shows done at once; it disappears on the next refetch. */
export function useSetTaskDone(familyId: string) {
  const { api } = useServices();
  const qc = useQueryClient();
  const key = planningKeys.tasks(familyId);
  return useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      unwrap(
        api.PATCH("/v1/families/{family_id}/tasks/{task_id}", {
          params: { path: { family_id: familyId, task_id: id } },
          body: { done },
        }),
      ),
    onMutate: async ({ id, done }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Task[]>(key);
      qc.setQueryData<Task[]>(key, (tasks) => tasks?.map((t) => (t.id === id ? { ...t, done } : t)));
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
  });
}
