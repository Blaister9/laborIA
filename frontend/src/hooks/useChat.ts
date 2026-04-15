import { useCallback, useState } from 'react'
import type { Message, ArticleSource } from '@/types'
import { generateId } from '@/lib/utils'
import { streamChat, streamDocument } from '@/lib/api'

interface UseChatProps {
  conversationId: string | null
  onMessage: (convId: string, msg: Message) => void
}

export function useChat({ conversationId, onMessage }: UseChatProps) {
  const [isStreaming, setIsStreaming] = useState(false)

  const processStream = useCallback(async (
    gen: AsyncGenerator<string>,
    convId: string,
    assistantMsgId: string,
  ) => {
    let content = ''
    let sources: ArticleSource[] | undefined

    onMessage(convId, { id: assistantMsgId, role: 'assistant', content: '', isStreaming: true, timestamp: new Date() })

    try {
      for await (const raw of gen) {
        if (!raw) continue
        let event: { type: string; content?: string; sources?: ArticleSource[] }
        try { event = JSON.parse(raw) } catch { continue }

        if (event.type === 'text') {
          content += event.content ?? ''
          onMessage(convId, { id: assistantMsgId, role: 'assistant', content, sources, isStreaming: true, timestamp: new Date() })
        } else if (event.type === 'sources') {
          sources = event.sources
          onMessage(convId, { id: assistantMsgId, role: 'assistant', content, sources, isStreaming: true, timestamp: new Date() })
        } else if (event.type === 'error') {
          onMessage(convId, { id: assistantMsgId, role: 'assistant', content: content || event.content || '', error: event.content, isStreaming: false, timestamp: new Date() })
          return
        } else if (event.type === 'done') {
          break
        }
      }
    } finally {
      onMessage(convId, { id: assistantMsgId, role: 'assistant', content, sources, isStreaming: false, timestamp: new Date() })
      setIsStreaming(false)
    }
  }, [onMessage])

  const sendMessage = useCallback(async (query: string, convId?: string) => {
    const id = convId ?? conversationId
    if (!id || isStreaming || !query.trim()) return
    const userMsg: Message = { id: generateId(), role: 'user', content: query, timestamp: new Date() }
    onMessage(id, userMsg)
    setIsStreaming(true)
    const assistantMsgId = generateId()
    await processStream(streamChat({ query }), id, assistantMsgId)
  }, [conversationId, isStreaming, onMessage, processStream])

  const uploadDocument = useCallback(async (file: File, question: string, convId?: string) => {
    const id = convId ?? conversationId
    if (!id || isStreaming) return
    const userMsg: Message = {
      id: generateId(), role: 'user',
      content: `📄 **${file.name}**\n\n${question}`,
      timestamp: new Date(),
    }
    onMessage(id, userMsg)
    setIsStreaming(true)
    const assistantMsgId = generateId()
    await processStream(streamDocument(file, question), id, assistantMsgId)
  }, [conversationId, isStreaming, onMessage, processStream])

  return { isStreaming, sendMessage, uploadDocument }
}
