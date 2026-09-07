'use client'

/**
 * Native classroom player — renders an OpenMAIC classroom (stage + scenes) inside Open
 * Notebook with @openmaic/renderer, so it inherits the app theme instead of an iframe.
 * Supports slide scenes (teacher narration steps with spotlight / laser effects) and quiz
 * scenes (single / multiple choice, short answer with reveal). Interactive / PBL scenes
 * fall back to the sidecar page via the "Open in new tab" link.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SlideCanvas, type SlideEffects } from '@openmaic/renderer'
import type { Action, Scene, Slide, QuizQuestion } from '@openmaic/dsl'
import { ChevronLeft, ChevronRight, ExternalLink, Pause, Play, GraduationCap, CheckCircle2, XCircle, Volume2, VolumeX, MessageCircleQuestion } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { TeacherChat, type TeacherAction } from '@/components/learn/TeacherChat'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

export interface ClassroomDocument {
  id: string
  stage: { id: string; name?: string; style?: string }
  scenes: Scene[]
  createdAt?: string
}

type AnyScene = Scene & { content: { type: string; canvas?: Slide; questions?: QuizQuestion[] } }

// Reading speed used to auto-advance narration when there is no TTS audio.
const WORDS_PER_SECOND = 2.6
const MIN_STEP_MS = 1800

function speechDurationMs(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return Math.max(MIN_STEP_MS, (words / WORDS_PER_SECOND) * 1000)
}

function effectsFromAction(action?: Action): SlideEffects {
  if (!action) return {}
  if (action.type === 'spotlight') return { spotlight: { elementId: action.elementId, dimness: action.dimOpacity } }
  if (action.type === 'laser') return { laser: { elementId: action.elementId, color: action.color } }
  return {}
}

/** Group actions into narration steps: each speech action carries the effects that precede it. */
type SpeechWithAudio = Extract<Action, { type: 'speech' }> & { audioUrl?: string }

function buildSteps(actions: Action[] | undefined) {
  const steps: { speech?: string; audioUrl?: string; effect?: Action }[] = []
  let pendingEffect: Action | undefined
  for (const a of actions ?? []) {
    if (a.type === 'speech') {
      steps.push({ speech: a.text, audioUrl: (a as SpeechWithAudio).audioUrl, effect: pendingEffect })
      pendingEffect = undefined
    } else if (a.type === 'spotlight' || a.type === 'laser') {
      pendingEffect = a
    }
  }
  if (pendingEffect) steps.push({ effect: pendingEffect })
  return steps
}

export interface QuizResult {
  answers: Record<string, string[]>
  correct: number
  total: number
  wrong: string[]
}

export function ClassroomPlayer({
  doc,
  sessionId,
  externalUrl,
  className,
  initialSceneIndex = 0,
  onProgress,
  onQuizResult,
  onComplete,
  completed = false,
}: {
  doc: ClassroomDocument
  /** Learning session id; enables "Ask the teacher" chat when set. */
  sessionId?: string
  externalUrl?: string | null
  className?: string
  initialSceneIndex?: number
  onProgress?: (sceneIndex: number, sceneId: string) => void
  onQuizResult?: (sceneId: string, result: QuizResult) => void
  onComplete?: () => void
  completed?: boolean
}) {
  const { t } = useTranslation()
  const scenes = useMemo(() => [...doc.scenes].sort((a, b) => a.order - b.order) as AnyScene[], [doc.scenes])
  const [sceneIdx, setSceneIdx] = useState(() => Math.min(Math.max(0, initialSceneIndex), Math.max(0, doc.scenes.length - 1)))
  const [stepIdx, setStepIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [teacherEffect, setTeacherEffect] = useState<Action | undefined>(undefined)
  const [quizResults, setQuizResults] = useState<Record<string, QuizResult>>({})
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const hasAudio = useMemo(() => scenes.some((sc) => (sc.actions ?? []).some((a) => (a as SpeechWithAudio).audioUrl)), [scenes])

  const scene = scenes[sceneIdx]
  const steps = useMemo(() => buildSteps(scene?.actions as Action[] | undefined), [scene])

  useEffect(() => {
    if (scene) onProgress?.(sceneIdx, scene.id)
    setTeacherEffect(undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneIdx, scene?.id])
  const step = steps[stepIdx]

  // A teacher answer can point at the slide (spotlight / laser); it overrides the step's own
  // effect until the learner moves on, and pauses autoplay so the pointer is visible.
  const onTeacherAction = useCallback((a: TeacherAction) => {
    if (a.actionName === 'spotlight' || a.actionName === 'laser') {
      setPlaying(false)
      setTeacherEffect({ id: `teacher-${Date.now()}`, actionName: a.actionName, params: a.params } as unknown as Action)
    }
  }, [])

  const goScene = useCallback(
    (i: number) => {
      setSceneIdx(Math.max(0, Math.min(scenes.length - 1, i)))
      setStepIdx(0)
    },
    [scenes.length]
  )

  const next = useCallback(() => {
    if (stepIdx < steps.length - 1) setStepIdx((s) => s + 1)
    else if (sceneIdx < scenes.length - 1) goScene(sceneIdx + 1)
    else setPlaying(false)
  }, [stepIdx, steps.length, sceneIdx, scenes.length, goScene])

  const prev = useCallback(() => {
    if (stepIdx > 0) setStepIdx((s) => s - 1)
    else if (sceneIdx > 0) {
      const prevScene = scenes[sceneIdx - 1]
      const prevSteps = buildSteps(prevScene?.actions as Action[] | undefined)
      setSceneIdx(sceneIdx - 1)
      setStepIdx(Math.max(0, prevSteps.length - 1))
    }
  }, [stepIdx, sceneIdx, scenes])

  // Narration audio: play the step's clip; when playing, advance on `ended`.
  // Without audio (or muted), autoplay advances after the reading-time estimate.
  useEffect(() => {
    const el = audioRef.current
    if (el) { el.pause(); el.removeAttribute('src'); el.load() }
    if (!scene || scene.type !== 'slide') return
    const url = step?.audioUrl
    if (url && !muted && el) {
      el.src = url
      el.play().catch(() => { /* autoplay may be blocked until user interaction */ })
      if (playing) {
        const onEnded = () => next()
        el.addEventListener('ended', onEnded)
        return () => el.removeEventListener('ended', onEnded)
      }
      return
    }
    if (!playing) return
    const ms = step?.speech ? speechDurationMs(step.speech) : MIN_STEP_MS
    const id = setTimeout(next, ms)
    return () => clearTimeout(id)
  }, [playing, muted, scene, step, next])

  useEffect(() => {
    if (!playing) audioRef.current?.pause()
    else if (audioRef.current?.src && audioRef.current.paused) audioRef.current.play().catch(() => {})
  }, [playing])

  // Keyboard navigation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); next() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev])

  if (!scene) return null
  const canvas = scene.content.type === 'slide' ? scene.content.canvas : undefined
  const isQuiz = scene.content.type === 'quiz'
  const unsupported = !canvas && !isQuiz
  const isLast = sceneIdx === scenes.length - 1
  const activeEffect = teacherEffect ?? step?.effect

  return (
    <div className={cn('flex flex-col gap-3 h-full min-h-0', className)}>
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-shrink-0">
        <div className="min-w-0 flex items-center gap-2">
          <Badge variant="secondary" className="font-mono">{sceneIdx + 1}/{scenes.length}</Badge>
          <h2 className="font-display text-lg font-semibold tracking-tight truncate">{scene.title}</h2>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {sessionId && (
            <Button variant={chatOpen ? 'secondary' : 'outline'} size="sm" onClick={() => setChatOpen((o) => !o)} aria-pressed={chatOpen}>
              <MessageCircleQuestion className="h-4 w-4 mr-1.5" />
              {t('learn.chat.askTeacher')}
            </Button>
          )}
          {externalUrl && (
            <Button variant="ghost" size="sm" asChild>
              <a href={externalUrl} target="_blank" rel="noopener noreferrer" title={t('learn.openInNewTab')}>
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          )}
        </div>
      </div>

      {/* Stage */}
      <div className={cn('flex-1 min-h-0 grid gap-3', chatOpen ? 'grid-cols-[minmax(0,1fr)_minmax(280px,34%)]' : 'grid-cols-1')}>
      <div className="min-h-0 grid grid-rows-[minmax(0,1fr)_auto] gap-3">
        <div className="min-h-0 rounded-xl border bg-card shadow-soft overflow-hidden flex items-center justify-center p-3">
          {canvas ? (
            <div className="w-full h-full flex items-center justify-center">
              <div className="w-full max-h-full" style={{ aspectRatio: `${1 / (canvas.viewportRatio || 0.5625)}` }}>
                <SlideCanvas key={scene.id} slide={canvas} effects={effectsFromAction(activeEffect)} className="w-full h-full" chrome={false} canvasPercentage={100} />
              </div>
            </div>
          ) : isQuiz ? (
            <QuizView
              key={scene.id}
              questions={scene.content.questions ?? []}
              onResult={(r) => {
                setQuizResults((q) => ({ ...q, [scene.id]: r }))
                onQuizResult?.(scene.id, r)
              }}
            />
          ) : (
            <div className="text-center text-sm text-muted-foreground p-8">
              <p>{t('learn.player.unsupportedScene', { type: scene.content.type })}</p>
              {externalUrl && (
                <Button variant="outline" size="sm" className="mt-3" asChild>
                  <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />{t('learn.openInNewTab')}
                  </a>
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Teacher + transport */}
        <div className="rounded-xl border bg-card shadow-soft px-3 py-2 flex items-start gap-3">
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-teal-tint text-teal flex items-center justify-center mt-0.5">
            <GraduationCap className="h-4 w-4" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-muted-foreground">{t('learn.player.teacher')}</p>
            <p className="text-sm leading-relaxed max-h-14 overflow-y-auto pr-1">
              {unsupported ? '' : step?.speech ?? (isQuiz ? t('learn.player.quizIntro') : t('learn.player.noNarration'))}
            </p>
            {steps.length > 1 && (
              <div className="mt-2 flex gap-1">
                {steps.map((_, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setStepIdx(i)}
                    className={cn('h-1 flex-1 rounded-full transition-colors', i <= stepIdx ? 'bg-primary' : 'bg-muted')}
                    aria-label={`${i + 1}`}
                  />
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            {hasAudio && (
              <Button variant="ghost" size="sm" onClick={() => setMuted((m) => !m)} aria-label={muted ? t('learn.player.unmute') : t('learn.player.mute')}>
                {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={prev} disabled={sceneIdx === 0 && stepIdx === 0} aria-label={t('learn.player.previous')}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant={playing ? 'secondary' : 'default'} size="sm" onClick={() => setPlaying((p) => !p)} aria-label={playing ? t('learn.player.pause') : t('learn.player.play')}>
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
            {isLast && stepIdx >= steps.length - 1 ? (
              <Button size="sm" variant={completed ? 'secondary' : 'default'} onClick={onComplete} disabled={completed}>
                <CheckCircle2 className="h-4 w-4 mr-1.5" />
                {completed ? t('learn.player.completed') : t('learn.player.markComplete')}
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={next} aria-label={t('learn.player.next')}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
      {chatOpen && sessionId && (
        <TeacherChat
          sessionId={sessionId}
          currentSceneId={scene.id}
          quizResults={Object.keys(quizResults).length ? quizResults : undefined}
          onAction={onTeacherAction}
          onClose={() => setChatOpen(false)}
          className="min-h-0"
        />
      )}
      </div>

      <audio ref={audioRef} preload="auto" className="hidden" />

      {/* Scene strip */}
      <div className="flex gap-1.5 overflow-x-auto flex-shrink-0 pb-0.5">
        {scenes.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => goScene(i)}
            className={cn(
              'text-xs px-2.5 py-1 rounded-full border whitespace-nowrap transition-colors',
              i === sceneIdx ? 'bg-primary text-primary-foreground border-primary' : 'bg-card hover:bg-accent'
            )}
          >
            {i + 1}. {s.title}
          </button>
        ))}
      </div>
    </div>
  )
}

function QuizView({ questions, onResult }: { questions: QuizQuestion[]; onResult?: (r: QuizResult) => void }) {
  const { t } = useTranslation()
  const [answers, setAnswers] = useState<Record<string, string[]>>({})
  const [shortAnswers, setShortAnswers] = useState<Record<string, string>>({})
  const [revealed, setRevealed] = useState(false)

  const toggle = (q: QuizQuestion, value: string) => {
    setAnswers((prev) => {
      const cur = prev[q.id] ?? []
      if (q.type === 'single') return { ...prev, [q.id]: [value] }
      return { ...prev, [q.id]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] }
    })
  }
  const isCorrect = (q: QuizQuestion) => {
    if (!q.answer || q.answer.length === 0) return null
    const got = [...(answers[q.id] ?? [])].sort().join('|')
    const want = [...q.answer].sort().join('|')
    return got === want
  }
  const gradableQs = questions.filter((q) => q.type !== 'short_answer' && q.answer?.length)
  const score = gradableQs.filter((q) => isCorrect(q) === true).length
  const gradable = gradableQs.length
  const reveal = () => {
    setRevealed(true)
    onResult?.({
      answers,
      correct: score,
      total: gradable,
      wrong: gradableQs.filter((q) => isCorrect(q) !== true).map((q) => q.id),
    })
  }

  return (
    <div className="w-full h-full overflow-y-auto space-y-5 p-2">
      {questions.map((q, qi) => {
        const ok = revealed ? isCorrect(q) : null
        return (
          <div key={q.id} className="rounded-lg border bg-background p-4 space-y-3">
            <div className="flex items-start gap-2">
              <Badge variant="secondary" className="font-mono">{qi + 1}</Badge>
              <p className="font-medium leading-snug">{q.question}</p>
              {ok === true && <CheckCircle2 className="h-5 w-5 text-primary ml-auto flex-shrink-0" />}
              {ok === false && <XCircle className="h-5 w-5 text-destructive ml-auto flex-shrink-0" />}
            </div>
            {q.type === 'short_answer' ? (
              <Textarea rows={3} value={shortAnswers[q.id] ?? ''} onChange={(e) => setShortAnswers((p) => ({ ...p, [q.id]: e.target.value }))} placeholder={t('learn.player.yourAnswer')} />
            ) : (
              <div className="space-y-2">
                {(q.options ?? []).map((o) => {
                  const chosen = (answers[q.id] ?? []).includes(o.value)
                  const correct = revealed && q.answer?.includes(o.value)
                  return (
                    <label key={o.value} className={cn('flex items-center gap-3 rounded-md border px-3 py-2 cursor-pointer transition-colors', chosen && 'border-primary bg-primary/5', correct && 'border-primary bg-fern-tint')}>
                      <Checkbox checked={chosen} onCheckedChange={() => toggle(q, o.value)} />
                      <span className="font-mono text-xs text-muted-foreground w-5">{o.value}</span>
                      <span className="text-sm">{o.label}</span>
                    </label>
                  )
                })}
              </div>
            )}
            {revealed && (q.analysis || (q.type === 'short_answer' && q.answer?.length)) && (
              <div className="rounded-md bg-excerpt-wash p-3 text-sm">
                {q.type === 'short_answer' && q.answer?.length ? <p className="font-medium mb-1">{t('learn.player.modelAnswer')}: {q.answer.join('; ')}</p> : null}
                {q.analysis && <p className="text-muted-foreground">{q.analysis}</p>}
              </div>
            )}
          </div>
        )
      })}
      <div className="flex items-center gap-3">
        <Button onClick={reveal} disabled={revealed}>{t('learn.player.checkAnswers')}</Button>
        {revealed && gradable > 0 && (
          <span className="text-sm text-muted-foreground">{t('learn.player.score', { score, total: gradable })}</span>
        )}
      </div>
    </div>
  )
}
