import { useState, useCallback } from 'react'
import type { Conversation, Message } from '@/types'
import { generateId, truncate } from '@/lib/utils'

const STORAGE_KEY = 'laboria_conversations'

function load(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw).map((c: Conversation) => ({
      ...c,
      createdAt: new Date(c.createdAt),
      updatedAt: new Date(c.updatedAt),
      messages: c.messages.map((m: Message) => ({ ...m, timestamp: new Date(m.timestamp) })),
    }))
  } catch { return [] }
}

function save(convs: Conversation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
}

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>(load)
  const [activeId, setActiveId] = useState<string | null>(
    () => load()[0]?.id ?? null
  )

  const active = conversations.find(c => c.id === activeId) ?? null

  const newConversation = useCallback((): string => {
    const id = generateId()
    const conv: Conversation = {
      id, title: 'Nueva consulta',
      messages: [], createdAt: new Date(), updatedAt: new Date(),
    }
    setConversations(prev => {
      const next = [conv, ...prev]
      save(next)
      return next
    })
    setActiveId(id)
    return id
  }, [])

  const upsertMessage = useCallback((convId: string, msg: Message) => {
    setConversations(prev => {
      const next = prev.map(c => {
        if (c.id !== convId) return c
        const exists = c.messages.find(m => m.id === msg.id)
        const messages = exists
          ? c.messages.map(m => m.id === msg.id ? msg : m)
          : [...c.messages, msg]
        // Auto-title from first user message
        const title = c.title === 'Nueva consulta' && msg.role === 'user'
          ? truncate(msg.content, 40)
          : c.title
        return { ...c, messages, title, updatedAt: new Date() }
      })
      save(next)
      return next
    })
  }, [])

  const deleteConversation = useCallback((id: string) => {
    setConversations(prev => {
      const next = prev.filter(c => c.id !== id)
      save(next)
      return next
    })
    setActiveId(prev => prev === id ? (conversations.find(c => c.id !== id)?.id ?? null) : prev)
  }, [conversations])

  return { conversations, active, activeId, setActiveId, newConversation, upsertMessage, deleteConversation }
}
