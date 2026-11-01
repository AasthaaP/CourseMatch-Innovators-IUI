// Two routes: "/" (the CourseMatch system) and "/baseline" (the study control, spec 29).
import { useCallback, useEffect, useState } from 'react'
import { USE_FIXTURES } from './api.js'
import { useEvents } from './hooks/useEvents.js'
import { useProfile, useStudentId } from './hooks/useProfile.js'
import { useRecommend } from './hooks/useRecommend.js'
import Onboarding from './components/Onboarding/Onboarding.jsx'
import ResultList, { ExampleChips } from './components/ResultList/ResultList.jsx'
import ChatPanel from './components/ChatPanel/ChatPanel.jsx'
import BaselinePage from './components/Baseline/BaselinePage.jsx'

const EXAMPLES = ['machine learning for images', 'distributed cloud systems', 'security and privacy']

function SystemPage() {
  const [studentId, resetStudent] = useStudentId('system')
  const { status, profile, save, loadSample } = useProfile(studentId, resetStudent)
  const log = useEvents(studentId, 'system')
  const { state, run } = useRecommend(studentId)
  const [query, setQuery] = useState('')
  // false | 'required' (incomplete profile) | 'edit' (Edit profile). Onboarding stays open until Start or
  // Cancel, even though loading a sample already writes a complete profile on the server.
  const [editing, setEditing] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [clarification, setClarification] = useState(null)
  const needsOnboarding = status === 'ok' && (!profile?.stated?.program || !profile?.stated?.interests?.length)

  useEffect(() => { setClarification(state.status === 'ok' ? state.data?.clarification || null : null) }, [state])
  useEffect(() => { if (needsOnboarding) setEditing((e) => e || 'required') }, [needsOnboarding])

  const submit = useCallback((q) => {
    setQuery(q)
    if (q.trim()) run(q)
  }, [run])

  if (!studentId || status === 'loading') return <p className="p-6 text-muted">Loading…</p>
  if (status === 'error') return <p className="p-6 text-muted">Could not reach the server.</p>

  if (needsOnboarding || editing) {
    return (
      <div className="px-4 py-6">
        <h1 className="mx-auto mb-4 max-w-3xl text-xl font-semibold text-accent">CourseMatch</h1>
        <Onboarding profile={profile} onSave={save} onLoadSample={loadSample} log={log}
          onCancel={editing === 'edit' ? () => setEditing(false) : null}
          onDone={() => { setEditing(false); if (query.trim()) run(query) }} />
      </div>
    )
  }

  const answer = (option) => {
    log('clarify_answered', { query, payload: { option: option.id } })
    setClarification(null)
    run(query, { clarificationAnswer: option.id })
  }
  const dismiss = () => { log('clarify_dismissed', { query }); setClarification(null) }

  const chatPanel = (
    <ChatPanel studentId={studentId} clarification={clarification} onAnswer={answer} onDismissClarification={dismiss}
      onProfileChanged={() => query.trim() && run(query)} onNewQuery={submit} />
  )

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-4 flex items-center justify-between border-b border-line pb-3">
        <h1 className="text-xl font-semibold text-accent">CourseMatch</h1>
        <div className="flex items-center gap-4 text-sm">
          {USE_FIXTURES && <span className="text-xs text-muted">fixtures mode</span>}
          <button type="button" onClick={() => setEditing('edit')} className="text-accent underline">Edit profile</button>
          <button type="button" onClick={() => setChatOpen(true)} className="rounded border border-line px-3 py-1 lg:hidden">Chat</button>
        </div>
      </header>
      <div className="grid gap-6 lg:grid-cols-3">
        <main className="lg:col-span-2">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(query) }}>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search courses in plain language" className="flex-1 rounded border border-line px-3 py-2" />
            <button className="rounded bg-accent px-4 py-2 text-white">Search</button>
          </form>
          <ExampleChips examples={EXAMPLES} onSearch={submit} />
          <div className="mt-4">
            <ResultList state={state} studentId={studentId} onRetry={() => submit(query)} onSearch={submit}
              examples={EXAMPLES} log={log} />
          </div>
        </main>
        <div className="hidden lg:block">{chatPanel}</div>
      </div>
      {chatOpen && (  // narrower than 1024px: the chat opens over the list (spec 26.1)
        <div className="fixed inset-0 z-30 flex justify-end bg-black/20 lg:hidden" onClick={() => setChatOpen(false)}>
          <div className="h-full w-full max-w-sm bg-white p-3" onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={() => setChatOpen(false)} className="mb-2 text-sm text-muted underline">Close</button>
            {chatPanel}
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  return window.location.pathname.startsWith('/baseline') ? <BaselinePage /> : <SystemPage />
}
