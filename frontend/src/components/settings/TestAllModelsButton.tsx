'use client'

import { CheckCircle2, Loader2, Plug, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTestAllModels } from '@/lib/hooks/use-models'
import { useTranslation } from '@/lib/hooks/use-translation'

/** "Test all" (fork): minimal real call against every registered model, results in a dialog. */
export function TestAllModelsButton() {
  const { t } = useTranslation()
  const testAll = useTestAllModels()

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => testAll.mutate()} disabled={testAll.isPending}>
        {testAll.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Plug className="h-4 w-4 mr-2" />}
        {testAll.isPending ? t('models.testingAll') : t('models.testAll')}
      </Button>
      <Dialog open={!!testAll.result} onOpenChange={(o) => !o && testAll.clearResult()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('models.testAllResults')}</DialogTitle>
            <DialogDescription>
              {t('models.testAllSummary', { passed: testAll.result?.passed ?? 0, failed: testAll.result?.failed ?? 0 })}
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-2 max-h-[60vh] overflow-y-auto">
            {testAll.result?.results.map((r) => (
              <li key={r.id} className="flex items-start gap-3 rounded-lg border p-3 text-sm">
                {r.success ? (
                  <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="font-mono text-xs">
                    {r.provider} / {r.name} <span className="text-muted-foreground">({r.type})</span>
                  </p>
                  <p className={r.success ? 'text-muted-foreground' : 'text-destructive break-words'}>{r.message}</p>
                </div>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  )
}
