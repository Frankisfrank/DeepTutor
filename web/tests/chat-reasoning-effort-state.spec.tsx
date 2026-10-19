import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import { ChatStateAdapterProvider, useChatStateAdapter } from '@/features/chat/ChatStateAdapter'
import { storeFailedSubmission } from '@/lib/failed-submissions'
import { updateRecoveryPrincipal } from '@/lib/recovery-principal'

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  requests: [] as Record<string, unknown>[],
}))

vi.mock('@/lib/session-api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/session-api')>()),
  getSession: mocks.getSession,
}))

vi.mock('@/features/chat/transport/UnifiedTurnClient', () => ({
  UnifiedTurnClient: class {
    connected = true
    connect() {}
    disconnect() {}
    setResumeState() {}
    send(message: Record<string, unknown>) {
      mocks.requests.push(message)
    }
  },
}))

const MODEL = { profile_id: 'profile-1', model_id: 'model-1' }

function session(reasoningEffort?: unknown) {
  return {
    id: 'session-1',
    session_id: 'session-1',
    title: 'Math',
    status: 'completed',
    created_at: 1,
    updated_at: 1,
    messages: [],
    preferences: {
      llm_selection: { ...MODEL, reasoning_effort: reasoningEffort },
    },
  }
}

function Harness() {
  const { state, loadSession, sendMessage, resendLastMessage, setLLMSelection } =
    useChatStateAdapter()
  return (
    <>
      <button onClick={() => void loadSession('session-1')}>Load</button>
      <button onClick={() => setLLMSelection({ ...MODEL, reasoning_effort: 'high' })}>High</button>
      <button onClick={() => sendMessage('Explain this')}>Send</button>
      <button onClick={() => void resendLastMessage()}>Resend</button>
      <output data-testid="selection">{JSON.stringify(state.llmSelection)}</output>
      <output data-testid="failed">{String(state.submissionFailed)}</output>
    </>
  )
}

function mount() {
  return render(
    <ChatStateAdapterProvider>
      <Harness />
    </ChatStateAdapterProvider>
  )
}

function start() {
  return mocks.requests.find(request => request.type === 'start_turn')
}

beforeEach(() => {
  updateRecoveryPrincipal({ enabled: false, authenticated: true })
  localStorage.clear()
  sessionStorage.clear()
  mocks.requests.length = 0
  mocks.getSession.mockReset().mockResolvedValue(session('xhigh'))
})

it.each(['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'adaptive'])(
  'restores saved %s effort and includes it in the next turn',
  async effort => {
    mocks.getSession.mockResolvedValue(session(effort))
    mount()
    fireEvent.click(screen.getByText('Load'))
    await waitFor(() => expect(screen.getByTestId('selection')).toHaveTextContent(effort))
    fireEvent.click(screen.getByText('Send'))
    expect(start()?.llm_selection).toEqual({ ...MODEL, reasoning_effort: effort })
  }
)

it.each([undefined, null, '', 'unsupported', 3])(
  'inherits the model default for an absent or malformed saved effort (%s)',
  async effort => {
    mocks.getSession.mockResolvedValue(session(effort))
    mount()
    fireEvent.click(screen.getByText('Load'))
    await waitFor(() => expect(screen.getByTestId('selection')).toHaveTextContent('profile-1'))
    fireEvent.click(screen.getByText('Send'))
    expect(start()?.llm_selection).toEqual(MODEL)
  }
)

it("uses a draft conversation's effort in its first turn", () => {
  mount()
  fireEvent.click(screen.getByText('High'))
  fireEvent.click(screen.getByText('Send'))
  expect(start()?.llm_selection).toEqual({ ...MODEL, reasoning_effort: 'high' })
})

it('replays a restored failed submission with its original effort', async () => {
  storeFailedSubmission('session-1', {
    content: 'Original question',
    capability: 'chat',
    requestSnapshot: {
      content: 'Original question',
      capability: 'chat',
      enabledTools: [],
      knowledgeBases: [],
      language: 'en',
      llmSelection: { ...MODEL, reasoning_effort: 'medium' },
    },
  })
  mount()
  fireEvent.click(screen.getByText('Load'))
  await waitFor(() => expect(screen.getByTestId('failed')).toHaveTextContent('true'))
  fireEvent.click(screen.getByText('High'))
  fireEvent.click(screen.getByText('Resend'))
  await waitFor(() => expect(start()).toBeDefined())
  expect(start()?.llm_selection).toEqual({ ...MODEL, reasoning_effort: 'medium' })
})
