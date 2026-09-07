'use client'

import { useState } from 'react'
import { Loader2, MonitorPlay, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useClassroomDocument, useUpdateLearningProgress } from '@/lib/hooks/use-learn'
import { useTranslation } from '@/lib/hooks/use-translation'
import { ClassroomPlayer } from './ClassroomPlayer'
import type { LearningSession } from '@/lib/api/learn'
import { cn } from '@/lib/utils'

/**
 * Native player by default; a toggle switches to the full OpenMAIC classroom (iframe) for the
 * multi-agent discussion, whiteboard and interactive scenes the native player does not cover.
 */
export function ClassroomView({ session, className }: { session: LearningSession; className?: string }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'native' | 'full'>('native')
  const doc = useClassroomDocument(mode === 'native' ? session.id : null)
  const progress = useUpdateLearningProgress()

  return (
    <div className={cn('flex flex-col gap-2 h-full min-h-0', className)}>
      <div className="flex items-center gap-1 flex-shrink-0 self-end">
        <Button variant={mode === 'native' ? 'secondary' : 'ghost'} size="sm" onClick={() => setMode('native')}>
          <Sparkles className="h-4 w-4 mr-1.5" />{t('learn.player.modeNative')}
        </Button>
        <Button variant={mode === 'full' ? 'secondary' : 'ghost'} size="sm" onClick={() => setMode('full')}>
          <MonitorPlay className="h-4 w-4 mr-1.5" />{t('learn.player.modeFull')}
        </Button>
      </div>
      {mode === 'full' ? (
        session.classroom_url ? (
          <iframe src={session.classroom_url} title={session.title} className="flex-1 w-full rounded-xl border bg-background" allow="microphone; autoplay; fullscreen" />
        ) : null
      ) : doc.isLoading ? (
        <div className="flex-1 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />{t('common.loading')}
        </div>
      ) : doc.isError || !doc.data ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
          <p>{t('learn.player.loadFailed')}</p>
          <Button variant="outline" size="sm" onClick={() => setMode('full')}>{t('learn.player.modeFull')}</Button>
        </div>
      ) : (
        <ClassroomPlayer
          doc={doc.data}
          sessionId={session.id}
          externalUrl={session.classroom_url}
          className="flex-1 min-h-0"
          initialSceneIndex={session.learner?.scene_index ?? 0}
          completed={!!session.completed_at}
          onProgress={(sceneIndex, sceneId) => progress.mutate({ sessionId: session.id, data: { scene_index: sceneIndex, scenes_seen: [sceneId] } })}
          onQuizResult={(sceneId, r) => progress.mutate({ sessionId: session.id, data: { quiz: { [sceneId]: r } } })}
          onComplete={() => progress.mutate({ sessionId: session.id, data: { completed: true } })}
        />
      )}
    </div>
  )
}
