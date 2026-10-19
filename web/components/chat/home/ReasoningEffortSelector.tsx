'use client'

import { Brain } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { LLMSelection } from '@/features/chat/model/protocol'
import { sameLLMSelection, type LLMOption } from '@/lib/llm-options'
import {
  reasoningEffortOptions,
  reasoningEffortOptionsFromSupportedLevels,
} from '@/lib/reasoning-effort'

export default function ReasoningEffortSelector({
  options,
  activeDefault,
  value,
  disabled = false,
  onChange,
}: {
  options: LLMOption[]
  activeDefault: LLMSelection | null
  value: LLMSelection | null
  disabled?: boolean
  onChange: (selection: LLMSelection) => void
}) {
  const { t } = useTranslation()
  const selection = value ?? activeDefault
  const model = options.find(option => sameLLMSelection(option, selection))
  if (!model || !selection) return null
  const choices = model.supported_reasoning_efforts
    ? reasoningEffortOptionsFromSupportedLevels(model.supported_reasoning_efforts)
    : reasoningEffortOptions(model.provider, model.model, model.reasoning_effort)
  const effort = selection.reasoning_effort ?? ''
  if (choices.length === 0 && !effort) return null
  const unavailable = Boolean(effort && !choices.some(choice => choice.value === effort))
  const modelDefault =
    t('Model default') + (model.reasoning_effort ? ` (${model.reasoning_effort})` : '')

  return (
    <label
      title={t('Reasoning effort')}
      className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg px-1.5 text-[12px] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/55"
    >
      <Brain size={14} aria-hidden="true" className="shrink-0" />
      <select
        aria-label={t('Reasoning effort')}
        aria-invalid={unavailable || undefined}
        disabled={disabled}
        value={effort}
        onChange={event => {
          const next: LLMSelection = {
            profile_id: selection.profile_id,
            model_id: selection.model_id,
          }
          if (event.target.value) next.reasoning_effort = event.target.value
          onChange(next)
        }}
        className="max-w-[140px] cursor-pointer bg-transparent py-1 outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <option value="">{modelDefault}</option>
        {choices
          .filter(choice => choice.value)
          .map(choice => (
            <option key={choice.value} value={choice.value}>
              {t(choice.label)}
            </option>
          ))}
        {unavailable && (
          <option value={effort} disabled>
            {effort} ({t('Unavailable')})
          </option>
        )}
      </select>
    </label>
  )
}
