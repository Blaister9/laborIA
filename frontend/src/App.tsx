import { useCallback, useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import { ChatContainer } from '@/components/chat/ChatContainer'
import { Sidebar } from '@/components/sidebar/Sidebar'
import { useConversations } from '@/hooks/useConversations'
import { useChat } from '@/hooks/useChat'
import type { Message } from '@/types'
import { checkHealth } from '@/lib/api'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  const { conversations, active, activeId, setActiveId, newConversation, upsertMessage, deleteConversation } =
    useConversations()

  const handleMessage = useCallback((convId: string, msg: Message) => {
    upsertMessage(convId, msg)
  }, [upsertMessage])

  const { isStreaming, sendMessage, uploadDocument } = useChat({
    conversationId: activeId,
    onMessage: handleMessage,
  })

  const handleSend = useCallback((text: string) => {
    const convId = activeId ?? newConversation()
    sendMessage(text, convId)
  }, [activeId, newConversation, sendMessage])

  const handleUpload = useCallback((file: File, question: string) => {
    const convId = activeId ?? newConversation()
    uploadDocument(file, question, convId)
  }, [activeId, newConversation, uploadDocument])

  // Health check on mount
  useEffect(() => {
    checkHealth().then(() => setBackendOk(true)).catch(() => setBackendOk(false))
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={newConversation}
        onDelete={deleteConversation}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 h-full">
        {/* Top bar */}
        <header className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden text-gray-500 hover:text-gray-700">
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-gray-900 truncate">
              {active?.title ?? 'LaborIA — Asistente Jurídico Laboral'}
            </h1>
          </div>
          {backendOk === false && (
            <span className="text-xs text-red-500 bg-red-50 px-2 py-1 rounded-full">
              Backend desconectado
            </span>
          )}
          {backendOk === true && (
            <span className="w-2 h-2 bg-green-500 rounded-full" title="Backend conectado" />
          )}
        </header>

        {/* Chat */}
        <main className="flex-1 overflow-hidden">
          <ChatContainer
            messages={active?.messages ?? []}
            isStreaming={isStreaming}
            onSend={handleSend}
            onUpload={handleUpload}
          />
        </main>
      </div>
    </div>
  )
}
