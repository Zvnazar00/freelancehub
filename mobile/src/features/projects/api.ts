import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, fetchAllPages, queryKeys } from '@/shared/api';
import { toProject, toTask } from '@/shared/api/mappers';
import type { WireProject, WireTask } from '@/shared/api/wire';
import type { Project, Task, TaskStatus } from '@/shared/types/domain';

import type { ProjectPayload } from './schema';

export function useProjects(filter: { clientId?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.projects.list(filter),
    queryFn: async ({ signal }) =>
      (await fetchAllPages<WireProject>('/projects', { client_id: filter.clientId }, signal)).map(toProject),
  });
}

export function useProject(id: string | undefined) {
  const qc = useQueryClient();
  return useQuery<Project, Error, Project, ReturnType<typeof queryKeys.projects.detail>>({
    queryKey: queryKeys.projects.detail(id ?? ''),
    enabled: Boolean(id),
    queryFn: async ({ signal }) => toProject(await api.request<WireProject>(`/projects/${id}`, { signal })),
    placeholderData: () => qc.getQueryData<Project[]>(queryKeys.projects.list())?.find((p) => p.id === id),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (p: ProjectPayload) =>
      toProject(
        await api.request<WireProject>('/projects', {
          method: 'POST',
          body: {
            client_id: p.clientId,
            name: p.name,
            billing_type: p.billingType,
            hourly_rate: p.hourlyRate,
            fixed_fee: p.fixedFee,
            budget_hours: p.budgetHours,
            color: p.color,
          },
        }),
      ),
    onSuccess: (project) => {
      qc.setQueryData(queryKeys.projects.detail(project.id), project);
      void qc.invalidateQueries({ queryKey: queryKeys.projects.all });
      void qc.invalidateQueries({ queryKey: queryKeys.clients.all }); // active project counts
    },
  });
}

export function useTasks(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tasks.byProject(projectId ?? ''),
    enabled: Boolean(projectId),
    queryFn: async ({ signal }) =>
      (await fetchAllPages<WireTask>('/tasks', { project_id: projectId }, signal)).map(toTask).sort((a, b) => a.position - b.position),
  });
}

export function useCreateTask(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (title: string) =>
      toTask(await api.request<WireTask>('/tasks', { method: 'POST', body: { project_id: projectId, title: title.trim() } })),
    onSuccess: (task) => {
      qc.setQueryData<Task[]>(queryKeys.tasks.byProject(projectId), (old) => [...(old ?? []), task]);
      void qc.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}

/** Toggles a task's status with an optimistic update and rollback on failure. */
export function useSetTaskStatus(projectId: string) {
  const qc = useQueryClient();
  const key = queryKeys.tasks.byProject(projectId);
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: TaskStatus }) =>
      toTask(await api.request<WireTask>(`/tasks/${id}`, { method: 'PATCH', body: { status } })),
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Task[]>(key);
      qc.setQueryData<Task[]>(key, (old) => old?.map((t) => (t.id === id ? { ...t, status } : t)));
      return { previous };
    },
    onError: (_e, _v, context) => {
      if (context?.previous) qc.setQueryData(key, context.previous);
    },
    onSuccess: (task) => qc.setQueryData<Task[]>(key, (old) => old?.map((t) => (t.id === task.id ? task : t))),
    onSettled: () => void qc.invalidateQueries({ queryKey: queryKeys.projects.detail(projectId) }),
  });
}
