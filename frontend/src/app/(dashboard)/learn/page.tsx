'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ExternalLink, GraduationCap, Loader2, Maximize2, Minimize2, Trash2, X } from 'lucide-react'
import { AppShell } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useAllLearningSessions, useDeleteLearningSession, useLearnStatus } from '@/lib/hooks/use-learn'
import { LearnDialog } from '../notebooks/components/LearnDialog'
import { ClassroomView } from '@/components/learn/ClassroomView'
import type { LearningSession } from '@/lib/api/learn'
import { cn } from '@/lib/utils'

const STATUS_KEYS = {
  pending: 'learn.status.pending',
  running: 'learn.status.running',
  succeeded: 'learn.status.succeeded',
  failed: 'learn.status.failed',
} as const

function statusVariant(status: LearningSession['status']) {
  if (status === 'succeeded') return 'default' as const
  if (status === 'failed') return 'destructive' as const
  return 'secondary' as const
}

export default function LearnPage() {
  const { t } = useTranslation()
  const status = useLearnStatus()
  const sessions = useAllLearningSessions()
  const notebooks = useNotebooks(false)
  const [pickedNotebook, setPickedNotebook] = useState<string>('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [active, setActive] = useState<LearningSession | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const remove = useDeleteLearningSession(active?.notebook_id ?? '')

  const list = sessions.data ?? []
  const available = status.data?.available ?? false
  const picked = notebooks.data?.find((n) => n.id === pickedNotebook)

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className={cn('p-6', fullscreen && 'p-2')}>
          {active?.classroom_url ? (
            <div className={cn('flex flex-col gap-3', fullscreen ? 'h-[calc(100vh-1rem)]' : 'h-[calc(100vh-3rem)]')}>
              <div className="flex items-center justify-between gap-3 flex-shrink-0">
                <div className="min-w-0">
                  <h1 className="font-display text-xl font-semibold tracking-tight truncate">{active.title}</h1>
                  <p className="text-xs text-muted-foreground truncate">{active.notebook_name}</p>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <Button variant="outline" size="sm" asChild>
                    <a href={active.classroom_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="h-4 w-4 mr-2" />
                      {t('learn.openInNewTab')}
                    </a>
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setFullscreen((f) => !f)}>
                    {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => { setActive(null); setFullscreen(false) }}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <ClassroomView session={active} className="flex-1 min-h-0" />
            </div>
          ) : (
            <div className="max-w-5xl mx-auto space-y-6">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h1 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2">
                    <GraduationCap className="h-6 w-6 text-primary" />
                    {t('learn.pageTitle')}
                  </h1>
                  <p className="text-muted-foreground mt-2">{t('learn.pageDesc')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Select value={pickedNotebook} onValueChange={setPickedNotebook}>
                    <SelectTrigger className="w-[260px]">
                      <SelectValue placeholder={t('learn.pickNotebook')} />
                    </SelectTrigger>
                    <SelectContent>
                      {(notebooks.data ?? []).map((n) => (
                        <SelectItem key={n.id} value={n.id}>{n.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button disabled={!picked || !available} onClick={() => setDialogOpen(true)}>
                    <GraduationCap className="h-4 w-4 mr-2" />
                    {t('learn.generate')}
                  </Button>
                </div>
              </div>

              {status.data && !available && (
                <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
                  <p className="font-medium">{t('learn.unavailable')}</p>
                  <p className="text-muted-foreground mt-1">{t('learn.unavailableDesc', { url: status.data.url })}</p>
                </div>
              )}

              {sessions.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('common.loading')}
                </div>
              ) : list.length === 0 ? (
                <Card className="p-10 text-center text-muted-foreground">
                  <GraduationCap className="h-10 w-10 mx-auto mb-3 opacity-40" />
                  <p>{t('learn.pageEmpty')}</p>
                </Card>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {list.map((s) => (
                    <Card key={s.id} className="p-5 flex flex-col gap-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium truncate">{s.title}</p>
                          {s.notebook_name && (
                            <Link href={`/notebooks/${s.notebook_id}`} className="text-xs text-muted-foreground hover:underline truncate block">
                              {s.notebook_name}
                            </Link>
                          )}
                        </div>
                        <Badge variant={statusVariant(s.status)}>{t(STATUS_KEYS[s.status] ?? STATUS_KEYS.pending)}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">{s.requirement}</p>
                      {(s.status === 'running' || s.status === 'pending') && (
                        <div className="space-y-1">
                          <Progress value={s.progress ?? 0} />
                          <p className="text-xs text-muted-foreground">{s.message}</p>
                        </div>
                      )}
                      {s.status === 'failed' && s.error && (
                        <p className="text-xs text-destructive break-words line-clamp-3">{s.error}</p>
                      )}
                      <div className="flex gap-2 mt-auto pt-1">
                        {s.status === 'succeeded' && s.classroom_url && (
                          <Button size="sm" onClick={() => setActive(s)}>{t('learn.open')}</Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive ml-auto"
                          onClick={() => remove.mutate(s.id)}
                          disabled={remove.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {picked && (
        <LearnDialog
          notebookId={picked.id}
          notebookName={picked.name}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
        />
      )}
    </AppShell>
  )
}
