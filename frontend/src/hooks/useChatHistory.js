import { useCallback, useEffect, useState } from 'react'

// Chat messages for one student, kept above the chat panel so they survive the profile page, Edit and a
// reload. Stored in this browser only (localStorage), per student id; the server keeps only chat_sent events.
const MAX = 200
const keyFor = (studentId) => `coursematch_chat_${studentId}`

function read(studentId) {
  if (!studentId) return []
  try {
    const v = JSON.parse(localStorage.getItem(keyFor(studentId)) || '[]')
    return Array.isArray(v) ? v : []
  } catch { return [] }
}

export function useChatHistory(studentId) {
  const [messages, setMessagesState] = useState(() => read(studentId))
  useEffect(() => { setMessagesState(read(studentId)) }, [studentId])

  const setMessages = useCallback((update) => {
    setMessagesState((prev) => {
      const next = (typeof update === 'function' ? update(prev) : update).slice(-MAX)
      try { if (studentId) localStorage.setItem(keyFor(studentId), JSON.stringify(next)) } catch { /* private mode */ }
      return next
    })
  }, [studentId])

  return [messages, setMessages]
}
