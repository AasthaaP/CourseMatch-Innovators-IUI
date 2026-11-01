// Chat panel (spec 28.1) and the clarification prompt (28.2). The backend logs chat_sent (spec 23.2).
// Chat works without an API key (the backend's rule parser answers). Only a 503 from /api/chat replaces the
// input with the unavailable message; the rest of the page keeps working.
import { useState } from 'react'
import { chat } from '../../api.js'
import Clarification from '../Clarification/Clarification.jsx'

const UNAVAILABLE = 'Chat is unavailable. No API key is configured.'

export default function ChatPanel({ studentId, clarification, onAnswer, onDismissClarification, onProfileChanged, onNewQuery }) {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [unavailable, setUnavailable] = useState(null)

  const send = async (e) => {
    e.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setText(''); setBusy(true)
    setMessages((m) => [...m, { from: 'you', text: message }])
    const r = await chat(studentId, message)
    setBusy(false)
    if (!r.ok) {
      if (r.status === 503) setUnavailable(r.error === 'no_api_key' ? UNAVAILABLE : 'Chat is unavailable right now.')
      else setMessages((m) => [...m, { from: 'system', text: 'Could not reach the server.' }])
      return
    }
    setMessages((m) => [...m, { from: 'system', text: r.data.reply }])
    if (r.data.action === 'new_query' && r.data.new_query) onNewQuery(r.data.new_query)
    else if (r.data.profile_changed) onProfileChanged()
  }

  return (
    <aside data-testid="chat-panel" className="flex h-full min-h-[24rem] flex-col rounded border border-line p-4 text-sm">
      <h2 className="mb-2 font-semibold">Chat</h2>
      <p className="mb-2 text-xs text-muted">Change your interests or your search in plain words. Chat never ranks courses.</p>
      <div className="flex-1 space-y-2 overflow-y-auto">
        {messages.map((m, i) => (
          <p key={i} className={`whitespace-pre-line rounded px-2 py-1 ${m.from === 'you' ? 'ml-6 bg-accent/5' : 'mr-6 bg-notsure-bg'}`}>{m.text}</p>
        ))}
        {clarification && <Clarification clarification={clarification} onAnswer={onAnswer} onDismiss={onDismissClarification} />}
      </div>
      {unavailable ? (
        <p className="mt-3 rounded bg-notsure-bg px-3 py-2 text-muted">{unavailable}</p>
      ) : (
        <form onSubmit={send} className="mt-3 flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. I care more about systems now"
            className="flex-1 rounded border border-line px-2 py-1.5" />
          <button disabled={busy} className="rounded bg-accent px-3 py-1.5 text-white disabled:opacity-40">Send</button>
        </form>
      )}
    </aside>
  )
}
