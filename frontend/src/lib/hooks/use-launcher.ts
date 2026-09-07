import { useMutation, useQuery } from '@tanstack/react-query'
import { appApi } from '@/lib/api/app'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'

/** Whether the API runs under the local launcher and this browser may stop it. */
export function useLauncherStatus() {
  return useQuery({
    queryKey: ['app', 'launcher'],
    queryFn: appApi.launcherStatus,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

/** Stops every local service (DB, API, worker, UI, Learn sidecar) and closes the launcher app. */
export function useShutdownApp() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: appApi.shutdown,
    onSuccess: () => {
      toast({ title: t('app.quitting'), description: t('app.quittingDesc') })
      // Give the toast a moment, then replace the page so the user is not left on a dead app.
      setTimeout(() => {
        document.body.innerHTML = `<div style="font-family:system-ui;padding:3rem;text-align:center;color:#666"><h1>${t('app.stopped')}</h1><p>${t('app.stoppedDesc')}</p></div>`
      }, 1500)
    },
    onError: (error: unknown) => {
      toast({ title: t('app.quitFailed'), description: getApiErrorKey(error, t('common.error')), variant: 'destructive' })
    },
  })
}
