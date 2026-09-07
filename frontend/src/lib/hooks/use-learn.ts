import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { learnApi, LearningSession, LearningSessionCreate } from '@/lib/api/learn'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'

export const LEARN_KEYS = {
  status: ['learn', 'status'] as const,
  sessions: (notebookId: string) => ['learn', 'sessions', notebookId] as const,
  all: ['learn', 'sessions'] as const,
}

function hasActive(sessions?: LearningSession[]) {
  return !!sessions?.some((s) => s.status === 'pending' || s.status === 'running')
}

export function useLearnStatus() {
  return useQuery({
    queryKey: LEARN_KEYS.status,
    queryFn: learnApi.status,
    staleTime: 60_000,
    retry: false,
  })
}

export function useAllLearningSessions() {
  return useQuery({
    queryKey: LEARN_KEYS.all,
    queryFn: learnApi.listAll,
    refetchInterval: (query) => (hasActive(query.state.data) ? 5_000 : false),
  })
}

export function useLearningSessions(notebookId: string, enabled = true) {
  return useQuery({
    queryKey: LEARN_KEYS.sessions(notebookId),
    queryFn: () => learnApi.list(notebookId),
    enabled: enabled && !!notebookId,
    // The backend polls OpenMAIC on each list call; keep polling while a job runs.
    refetchInterval: (query) => (hasActive(query.state.data) ? 5_000 : false),
  })
}

export function useClassroomDocument(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: ['learn', 'classroom', sessionId],
    queryFn: () => learnApi.classroom(sessionId as string),
    enabled: !!sessionId,
    staleTime: 10 * 60 * 1000,
  })
}

export function useCreateLearningSession(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: LearningSessionCreate) => learnApi.create(notebookId, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: LEARN_KEYS.all })
      toast({ title: t('learn.generationStarted'), description: t('learn.generationStartedDesc') })
    },
    onError: (error: unknown) => {
      toast({
        title: t('learn.generationFailed'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteLearningSession(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (sessionId: string) => learnApi.delete(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: LEARN_KEYS.all })
      toast({ title: t('learn.deleted') })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}
