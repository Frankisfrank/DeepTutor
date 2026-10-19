import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import ReasoningEffortSelector from '@/components/chat/home/ReasoningEffortSelector'
import type { LLMOption } from '@/lib/llm-options'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const model: LLMOption = {
  profile_id: 'codex',
  model_id: 'sol',
  profile_name: 'Codex',
  model_name: 'Sol',
  model: 'gpt-6.1-sol',
  provider: 'openai_codex',
  reasoning_effort: 'medium',
  supported_reasoning_efforts: ['low', 'medium', 'high', 'ultra'],
  is_active_default: true,
}
const selection = { profile_id: 'codex', model_id: 'sol' }

it("offers the selected model's supported levels and changes only the conversation selection", () => {
  const onChange = vi.fn()
  render(
    <ReasoningEffortSelector
      options={[model]}
      activeDefault={selection}
      value={null}
      onChange={onChange}
    />
  )
  const control = screen.getByRole('combobox', { name: 'Reasoning effort' })
  expect(screen.getByRole('option', { name: 'ultra' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'Maximum' })).not.toBeInTheDocument()
  fireEvent.change(control, { target: { value: 'high' } })
  expect(onChange).toHaveBeenCalledWith({ ...selection, reasoning_effort: 'high' })
  expect(model.reasoning_effort).toBe('medium')
})

it("can return from an override to the model's saved default", () => {
  const onChange = vi.fn()
  render(
    <ReasoningEffortSelector
      options={[model]}
      activeDefault={selection}
      value={{ ...selection, reasoning_effort: 'high' }}
      onChange={onChange}
    />
  )
  const control = screen.getByRole('combobox', { name: 'Reasoning effort' })
  expect(control).toHaveValue('high')
  expect(screen.getByRole('option', { name: 'Model default (medium)' })).toBeInTheDocument()
  fireEvent.change(control, { target: { value: '' } })
  expect(onChange).toHaveBeenCalledWith(selection)
})

it('hides for a model without supported levels and locks during a running turn', () => {
  const onChange = vi.fn()
  const props = { activeDefault: selection, value: selection, onChange }
  const view = render(
    <ReasoningEffortSelector {...props} options={[{ ...model, supported_reasoning_efforts: [] }]} />
  )
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  view.rerender(<ReasoningEffortSelector {...props} options={[model]} disabled />)
  expect(screen.getByRole('combobox', { name: 'Reasoning effort' })).toBeDisabled()
})

it('keeps a stale saved level visible so the user can reset it', () => {
  render(
    <ReasoningEffortSelector
      options={[model]}
      activeDefault={selection}
      value={{ ...selection, reasoning_effort: 'max' }}
      onChange={vi.fn()}
    />
  )
  expect(screen.getByRole('combobox', { name: 'Reasoning effort' })).toHaveValue('max')
  expect(screen.getByRole('option', { name: 'max (Unavailable)' })).toBeDisabled()
})

it('allows resetting an override after reasoning support is removed', () => {
  const onChange = vi.fn()
  render(
    <ReasoningEffortSelector
      options={[{ ...model, supported_reasoning_efforts: [] }]}
      activeDefault={selection}
      value={{ ...selection, reasoning_effort: 'high' }}
      onChange={onChange}
    />
  )
  const control = screen.getByRole('combobox', { name: 'Reasoning effort' })
  fireEvent.change(control, { target: { value: '' } })
  expect(onChange).toHaveBeenCalledWith(selection)
})
