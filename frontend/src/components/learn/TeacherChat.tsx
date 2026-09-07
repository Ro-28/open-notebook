'use client'

/**
 * Ask the teacher (fork): chat with OpenMAIC's AI teacher about the classroom being played.
 * Streams SSE from POST /api/learn/{id}/chat (relayed to the sidecar's stateless /api/chat)
 * and hands slide actions (spotlight / laser) back to the player so the answer points at the
 * slide. Conversation state lives here; the backend keeps nothing.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { GraduationCap, Loader2, SendHorizontal, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

export interface TeacherAction {
  actionName: string
  params: Record<string, unknown>
}

interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
  pending?: boolean
  error?: string
}

function uid() {
  return Math.random().toString(36).slice(2, 10)
}

export function TeacherChat({
  sessionId,
  currentSceneId,
  quizResults,
  onAction,
  onClose,
  className,
}: {
  sessionId: string
  currentSceneId?: string
  quizResults?: Record<string, unknown>
  onAction?: (a: TeacherAction) => void
  onClose?: () => void
  className?: string
}) {
  const { t } = useTranslation()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (question: string) => {
      const q = question.trim()
      if (!q || busy) return
      setInput('')
      const userTurn: ChatTurn = { id: uid(), role: 'user', text: q }
      const replyId = uid()
      const history = [...turns, userTurn]
      setTurns([...history, { id: replyId, role: 'assistant', text: '', pending: true }])
      setBusy(true)
      const ctrl = new AbortController()
      abortRef.current = ctrl

      const patchReply = (fn: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => prev.map((x) => (x.id === replyId ? fn(x) : x)))

      try {
        const res = await fetch(`/api/learn/${encodeURIComponent(sessionId)}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          signal: ctrl.signal,
          body: JSON.stringify({
            messages: history.map((h) => ({ id: h.id, role: h.role, parts: [{ type: 'text', text: h.text }] })),
            current_scene_id: currentSceneId,
            quiz_results: quizResults,
          }),
        })
        if (!res.ok || !res.body) throw new Error(`${res.status} ${await res.text().catch(() => '')}`)
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\n\n')
          buffer = frames.pop() ?? ''
          for (const frame of frames) {
            const line = frame.split('\n').find((l) => l.startsWith('data:'))
            if (!line) continue
            let ev: { type?: string; data?: Record<string, unknown> }
            try {
              ev = JSON.parse(line.slice(5).trim())
            } catch {
              continue
            }
            const d = ev.data ?? {}
            if (ev.type === 'text_delta' && typeof d.content === 'string') {
              const piece = d.content
              // Segments arrive split around slide actions; keep a paragraph break between them.
              patchReply((x) => ({ ...x, text: x.text && /[.!?:]$/.test(x.text.trimEnd()) && !/^\s/.test(piece) ? `${x.text.trimEnd()}\n\n${piece}` : x.text + piece }))
            } else if (ev.type === 'action' && typeof d.actionName === 'string') {
              onAction?.({ actionName: d.actionName, params: (d.params as Record<string, unknown>) ?? {} })
            } else if (ev.type === 'error') {
              const msg = typeof d.message === 'string' ? d.message : t('learn.chat.error')
              patchReply((x) => ({ ...x, error: msg }))
            }
          }
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          const msg = e instanceof Error ? e.message : String(e)
          patchReply((x) => ({ ...x, error: msg }))
        }
      } finally {
        patchReply((x) => ({ ...x, pending: false, text: x.text || (x.error ? '' : t('learn.chat.empty')) }))
        setBusy(false)
        abortRef.current = null
      }
    },
    [busy, currentSceneId, onAction, quizResults, sessionId, t, turns]
  )

  const suggestions = [t('learn.chat.suggestExplain'), t('learn.chat.suggestExample'), t('learn.chat.suggestQuiz')]

  return (
    <div className={cn('flex flex-col min-h-0 rounded-xl border bg-card shadow-soft', className)}>
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-7 w-7 rounded-full bg-teal-tint text-teal flex items-center justify-center flex-shrink-0">
            <GraduationCap className="h-3.5 w-3.5" />
          </div>
          <p className="text-sm font-semibold truncate">{t('learn.chat.title')}</p>
        </div>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={t('common.close')}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-3">
        {turns.length === 0 && (
          <div className="text-sm text-muted-foreground space-y-3">
            <p>{t('learn.chat.intro')}</p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="text-xs px-2.5 py-1 rounded-full border bg-card hover:bg-accent transition-colors inline-flex items-center gap-1"
                >
                  <Sparkles className="h-3 w-3 text-teal" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className={cn('flex', turn.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div
              className={cn(
                'max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words',
                turn.role === 'user' ? 'bg-primary text-primary-foreground rounded-br-sm' : 'bg-muted/60 rounded-bl-sm'
              )}
            >
              {turn.text}
              {turn.pending && !turn.text && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              {turn.error && <p className="mt-1 text-xs text-destructive">{turn.error}</p>}
            </div>
          </div>
        ))}
      </div>

      <form
        className="flex items-end gap-2 p-2 border-t flex-shrink-0"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(input)
            }
          }}
          placeholder={t('learn.chat.placeholder')}
          rows={1}
          className="min-h-[38px] max-h-32 resize-none text-sm"
          disabled={busy}
        />
        <Button type="submit" size="sm" disabled={busy || !input.trim()} aria-label={t('learn.chat.send')}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
        </Button>
      </form>
    </div>
  )
}
