import { Plus, Trash2, MessageSquare, Scale, X } from 'lucide-react'
import type { Conversation } from '@/types'
import { cn, formatDate, truncate } from '@/lib/utils'

interface Props {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  isOpen: boolean
  onClose: () => void
}

export function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, isOpen, onClose }: Props) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/40 z-20 md:hidden" onClick={onClose} />
      )}

      <aside className={cn(
        'fixed md:relative inset-y-0 left-0 z-30 w-72 bg-gray-900 text-white flex flex-col transition-transform duration-300',
        'md:translate-x-0',
        isOpen ? 'translate-x-0' : '-translate-x-full',
      )}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-brand-400" />
            <span className="font-bold text-sm tracking-wide">LaborIA</span>
          </div>
          <button onClick={onClose} className="md:hidden text-gray-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* New chat button */}
        <div className="px-3 py-3">
          <button
            onClick={onNew}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gray-700 hover:bg-gray-800 transition-colors text-gray-300 hover:text-white"
          >
            <Plus className="w-4 h-4" />
            Nueva consulta
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto custom-scroll px-2 pb-4">
          {conversations.length === 0 ? (
            <p className="text-xs text-gray-500 text-center mt-4 px-3">
              No hay conversaciones aún.
            </p>
          ) : (
            <div className="space-y-0.5">
              {conversations.map(conv => (
                <ConvItem
                  key={conv.id}
                  conv={conv}
                  isActive={conv.id === activeId}
                  onSelect={() => { onSelect(conv.id); onClose() }}
                  onDelete={() => onDelete(conv.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500">
          CST + Ley 2466/2025 · No reemplaza asesoría legal
        </div>
      </aside>
    </>
  )
}

function ConvItem({ conv, isActive, onSelect, onDelete }:
  { conv: Conversation; isActive: boolean; onSelect: () => void; onDelete: (id: string) => void }) {
  const lastMsg = conv.messages[conv.messages.length - 1]
  return (
    <div
      className={cn(
        'group flex items-start gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors',
        isActive ? 'bg-gray-700 text-white' : 'hover:bg-gray-800 text-gray-400 hover:text-gray-200',
      )}
      onClick={onSelect}
    >
      <MessageSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 opacity-60" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate leading-tight">{conv.title}</p>
        {lastMsg && (
          <p className="text-xs opacity-50 truncate mt-0.5">{truncate(lastMsg.content, 35)}</p>
        )}
        <p className="text-xs opacity-40 mt-0.5">{formatDate(conv.updatedAt)}</p>
      </div>
      <button
        onClick={e => { e.stopPropagation(); onDelete(conv.id) }}
        className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all flex-shrink-0"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
