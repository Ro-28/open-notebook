'use client'

import { useState } from 'react'
import { ExternalLink, GraduationCap, Loader2, Maximize2, Minimize2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useCreateLearningSession,
  useDeleteLearningSession,
  useLearnStatus,
  useLearningSessions,
} from '@/lib/hooks/use-learn'
import type { LearningSession } from '@/lib/api/learn'
import { ClassroomView } from '@/components/learn/ClassroomView'
import { cn } from '@/lib/utils'

interface LearnDialogProps {
  notebookId: string
  notebookName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const STATUS_KEYS = {
  pending: 'learn.status.pending',
  running: 'learn.status.running',
  succeeded: 'learn.status.succeeded',
  failed: 'learn.status.failed',
} as const

function statusVariant(status: LearningSession['status']) {
  switch (status) {
    case 'succeeded':
      return 'default' as const
    case 'failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

export function LearnDialog({ notebookId, notebookName, open, onOpenChange }: LearnDialogProps) {
  const { t } = useTranslation()
  const status = useLearnStatus()
  const sessions = useLearningSessions(notebookId, open)
  const create = useCreateLearningSession(notebookId)
  const remove = useDeleteLearningSession(notebookId)

  const [requirement, setRequirement] = useState('')
  const [includeSources, setIncludeSources] = useState(true)
  const [includeInsights, setIncludeInsights] = useState(true)
  const [includeNotes, setIncludeNotes] = useState(true)
  const [enableTts, setEnableTts] = useState(false)
  const [liveRetrieval, setLiveRetrieval] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)

  const list = sessions.data ?? []
  const active = list.find((s) => s.id === activeId) ?? null
  const available = status.data?.available ?? false

  const handleGenerate = () => {
    create.mutate({
      requirement: requirement.trim() || undefined,
      include_sources: includeSources,
      include_insights: includeInsights,
      include_notes: includeNotes,
      enable_tts: enableTts,
      live_retrieval: liveRetrieval,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          'flex flex-col gap-4 overflow-hidden',
          fullscreen ? 'max-w-[98vw] w-[98vw] h-[96vh]' : 'max-w-5xl w-[95vw] h-[85vh]'
        )}
      >
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <GraduationCap className="h-5 w-5" />
            {t('learn.title')} · {notebookName}
          </DialogTitle>
          <DialogDescription>{t('learn.description')}</DialogDescription>
        </DialogHeader>

        {status.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('learn.checkingService')}
          </div>
        ) : !available ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm">
            <p className="font-medium">{t('learn.unavailable')}</p>
            <p className="text-muted-foreground mt-1">
              {t('learn.unavailableDesc', { url: status.data?.url ?? '' })}
            </p>
          </div>
        ) : null}

        {active ? (
          <div className="flex-1 min-h-0 flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2 flex-shrink-0">
              <div className="min-w-0">
                <p className="font-medium truncate">{active.title}</p>
                <p className="text-xs text-muted-foreground truncate">{active.requirement}</p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                {active.classroom_url && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={active.classroom_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="h-4 w-4 mr-2" />
                      {t('learn.openInNewTab')}
                    </a>
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => setFullscreen((f) => !f)}>
                  {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setActiveId(null)}>
                  {t('common.back')}
                </Button>
              </div>
            </div>
            {active.classroom_url ? (
              <ClassroomView session={active} className="flex-1 min-h-0" />
            ) : (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                {active.error ?? active.message ?? t('learn.notReady')}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-6 overflow-y-auto">
            {/* Generate form */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="learn-requirement">{t('learn.requirementLabel')}</Label>
                <Textarea
                  id="learn-requirement"
                  value={requirement}
                  onChange={(e) => setRequirement(e.target.value)}
                  placeholder={t('learn.requirementPlaceholder')}
                  rows={4}
                />
              </div>
              <div className="space-y-2">
                <Label>{t('learn.materials')}</Label>
                <div className="space-y-2 text-sm">
                  <label className="flex items-center gap-2">
                    <Checkbox checked={includeSources} onCheckedChange={(v) => setIncludeSources(v === true)} />
                    {t('learn.includeSources')}
                  </label>
                  <label className="flex items-center gap-2">
                    <Checkbox checked={includeInsights} onCheckedChange={(v) => setIncludeInsights(v === true)} />
                    {t('learn.includeInsights')}
                  </label>
                  <label className="flex items-center gap-2">
                    <Checkbox checked={includeNotes} onCheckedChange={(v) => setIncludeNotes(v === true)} />
                    {t('learn.includeNotes')}
                  </label>
                  <label className="flex items-center gap-2">
                    <Checkbox checked={liveRetrieval} onCheckedChange={(v) => setLiveRetrieval(v === true)} />
                    <span>
                      {t('learn.liveRetrieval')}
                      <span className="block text-xs text-muted-foreground">{t('learn.liveRetrievalDesc')}</span>
                    </span>
                  </label>
                  <label className="flex items-center gap-2">
                    <Checkbox checked={enableTts} onCheckedChange={(v) => setEnableTts(v === true)} />
                    {t('learn.enableTts')}
                  </label>
                </div>
              </div>
              <Button
                onClick={handleGenerate}
                disabled={!available || create.isPending || (!includeSources && !includeNotes)}
                className="w-full"
              >
                {create.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <GraduationCap className="h-4 w-4 mr-2" />
                )}
                {t('learn.generate')}
              </Button>
            </div>

            {/* Sessions list */}
            <div className="space-y-2">
              <Label>{t('learn.classrooms')}</Label>
              {sessions.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('common.loading')}
                </div>
              ) : list.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('learn.empty')}</p>
              ) : (
                <ul className="space-y-2">
                  {list.map((s) => (
                    <li key={s.id} className="rounded-md border p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium truncate">{s.title}</p>
                          <p className="text-xs text-muted-foreground line-clamp-2">{s.requirement}</p>
                        </div>
                        <Badge variant={statusVariant(s.status)}>{t(STATUS_KEYS[s.status] ?? STATUS_KEYS.pending)}</Badge>
                      </div>
                      {(s.status === 'running' || s.status === 'pending') && (
                        <div className="space-y-1">
                          <Progress value={s.progress ?? 0} />
                          <p className="text-xs text-muted-foreground">{s.message}</p>
                        </div>
                      )}
                      {s.status === 'failed' && s.error && (
                        <p className="text-xs text-destructive break-words">{s.error}</p>
                      )}
                      {s.material_stats && (
                        <p className="text-xs text-muted-foreground">
                          {t('learn.materialStats', {
                            sources: s.material_stats.sources ?? 0,
                            insights: s.material_stats.insights ?? 0,
                            notes: s.material_stats.notes ?? 0,
                          })}
                        </p>
                      )}
                      <div className="flex gap-2">
                        {s.status === 'succeeded' && s.classroom_url && (
                          <Button size="sm" onClick={() => setActiveId(s.id)}>
                            {t('learn.open')}
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={remove.isPending}
                          onClick={() => remove.mutate(s.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
