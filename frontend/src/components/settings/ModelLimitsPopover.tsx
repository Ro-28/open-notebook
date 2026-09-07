'use client'

import { useState } from 'react'
import { Loader2, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useUpdateModelLimits } from '@/lib/hooks/use-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { Model } from '@/lib/types/models'

/** Per-model limits editor (fork): context window drives the large-context switch; max tokens caps output. */
export function ModelLimitsPopover({ model }: { model: Model }) {
  const { t } = useTranslation()
  const update = useUpdateModelLimits()
  const [open, setOpen] = useState(false)
  const [ctx, setCtx] = useState(model.context_window ? String(model.context_window) : '')
  const [max, setMax] = useState(model.max_tokens ? String(model.max_tokens) : '')

  const save = () => {
    update.mutate(
      {
        id: model.id,
        data: {
          context_window: ctx.trim() ? Number(ctx) : null,
          max_tokens: max.trim() ? Number(max) : null,
        },
      },
      { onSuccess: () => setOpen(false) }
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="ml-0.5 opacity-0 group-hover/model:opacity-60 hover:!opacity-100 transition-opacity"
          title={t('models.limits')}
          onClick={(e) => e.stopPropagation()}
        >
          <SlidersHorizontal className="h-3 w-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-3" align="start" onClick={(e) => e.stopPropagation()}>
        <div>
          <p className="font-medium text-sm font-sans">{model.name}</p>
          <p className="text-xs text-muted-foreground font-sans">{t('models.limitsDesc')}</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`ctx-${model.id}`} className="text-xs font-sans">{t('models.contextWindow')}</Label>
          <Input id={`ctx-${model.id}`} inputMode="numeric" placeholder="200000" value={ctx} onChange={(e) => setCtx(e.target.value.replace(/[^0-9]/g, ''))} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`max-${model.id}`} className="text-xs font-sans">{t('models.maxTokens')}</Label>
          <Input id={`max-${model.id}`} inputMode="numeric" placeholder="8192" value={max} onChange={(e) => setMax(e.target.value.replace(/[^0-9]/g, ''))} />
        </div>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)} className="font-sans">{t('common.cancel')}</Button>
          <Button size="sm" onClick={save} disabled={update.isPending} className="font-sans">
            {update.isPending && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
            {t('common.save')}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
