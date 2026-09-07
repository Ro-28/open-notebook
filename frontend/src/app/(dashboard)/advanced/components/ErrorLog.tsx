'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Copy, RefreshCw, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { appApi } from '@/lib/api/app'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'

type Level = 'all' | 'warning' | 'error' | 'critical'

function levelOf(record: string): 'WARNING' | 'ERROR' | 'CRITICAL' | 'OTHER' {
  if (record.includes('| ERROR')) return 'ERROR'
  if (record.includes('| CRITICAL')) return 'CRITICAL'
  if (record.includes('| WARNING')) return 'WARNING'
  return 'OTHER'
}

export function ErrorLog() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [level, setLevel] = useState<Level>('all')

  const query = useQuery({
    queryKey: ['app', 'errors', level],
    queryFn: () => appApi.errors(200, level === 'all' ? undefined : level),
    refetchInterval: 15_000,
  })
  const clear = useMutation({
    mutationFn: appApi.clearErrors,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['app', 'errors'] })
      toast({ title: t('advanced.errorLogCleared') })
    },
  })

  const records = [...(query.data?.records ?? [])].reverse() // newest first
  const errorCount = records.filter((r) => levelOf(r) !== 'WARNING').length

  const copyAll = async () => {
    await navigator.clipboard.writeText((query.data?.records ?? []).join('\n'))
    toast({ title: t('advanced.errorLogCopied') })
  }

  return (
    <Card className="p-6">
      <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold tracking-tight flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-warn" />
              {t('advanced.errorLog')}
              {records.length > 0 && (
                <Badge variant={errorCount > 0 ? 'destructive' : 'secondary'}>{records.length}</Badge>
              )}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">{t('advanced.errorLogDesc')}</p>
            {query.data?.path && (
              <p className="text-xs text-muted-foreground font-mono mt-1 break-all">{query.data.path}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Select value={level} onValueChange={(v) => setLevel(v as Level)}>
              <SelectTrigger className="w-[130px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('advanced.errorLevelAll')}</SelectItem>
                <SelectItem value="warning">{t('advanced.errorLevelWarning')}</SelectItem>
                <SelectItem value="error">{t('advanced.errorLevelError')}</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => query.refetch()} disabled={query.isFetching}>
              <RefreshCw className={query.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
            </Button>
            <Button variant="outline" size="sm" onClick={copyAll} disabled={records.length === 0}>
              <Copy className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => clear.mutate()}
              disabled={records.length === 0 || clear.isPending}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {query.isLoading ? (
          <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
        ) : records.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {t('advanced.errorLogEmpty')}
          </div>
        ) : (
          <ul className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
            {records.map((record, i) => {
              const lvl = levelOf(record)
              const [head, ...rest] = record.split('\n')
              return (
                <li
                  key={i}
                  className="rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed"
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={
                        lvl === 'WARNING'
                          ? 'mt-1 h-2 w-2 shrink-0 rounded-full bg-warn'
                          : 'mt-1 h-2 w-2 shrink-0 rounded-full bg-destructive'
                      }
                    />
                    <span className="break-words whitespace-pre-wrap">{head}</span>
                  </div>
                  {rest.length > 0 && (
                    <details className="mt-1 ml-4">
                      <summary className="cursor-pointer text-muted-foreground">{t('advanced.errorLogTrace')}</summary>
                      <pre className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">{rest.join('\n')}</pre>
                    </details>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Card>
  )
}
