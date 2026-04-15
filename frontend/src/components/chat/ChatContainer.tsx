import { useEffect, useRef } from 'react'
import type { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { InputBar } from './InputBar'
import { Scale } from 'lucide-react'

interface Props {
  messages: Message[]
  isStreaming: boolean
  onSend: (text: string) => void
  onUpload: (file: File, question: string) => void
}

const EXAMPLES = [
  '¿Me despidieron sin justa causa después de 3 años, cuánto me deben?',
  '¿Cuánto es el recargo por trabajo dominical desde la reforma de 2025?',
  '¿Cuáles son las causales de despido con justa causa según el CST?',
  '¿Cuánto tiempo tengo para demandar si no me pagaron las cesantías?',
]

export function ChatContainer({ messages, isStreaming, onSend, onUpload }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scroll px-3 md:px-6 py-4">
        {messages.length === 0 ? (
          <EmptyState onExample={onSend} />
        ) : (
          <>
            {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <InputBar onSend={onSend} onUpload={onUpload} isDisabled={isStreaming} />
    </div>
  )
}

function EmptyState({ onExample }: { onExample: (t: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-8">
      <div className="w-14 h-14 bg-gradient-to-br from-brand-500 to-brand-700 rounded-2xl flex items-center justify-center mb-4 shadow-md">
        <Scale className="w-7 h-7 text-white" />
      </div>
      <h2 className="text-xl font-bold text-gray-900 mb-1">LaborIA</h2>
      <p className="text-gray-500 text-sm max-w-sm mb-6">
        Asistente jurídico especializado en derecho laboral colombiano.<br />
        Basado en el CST y la Ley 2466/2025.
      </p>
      <div className="grid gap-2 w-full max-w-md">
        {EXAMPLES.map(ex => (
          <button
            key={ex}
            onClick={() => onExample(ex)}
            className="text-left text-sm px-4 py-2.5 border border-gray-200 rounded-xl hover:border-brand-400 hover:bg-brand-50 transition-colors text-gray-700"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}
