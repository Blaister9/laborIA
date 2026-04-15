import { useState, useRef, useCallback } from 'react'
import type { KeyboardEvent } from 'react'
import { Send, Paperclip, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FileUpload } from '@/components/upload/FileUpload'

interface Props {
  onSend: (text: string) => void
  onUpload: (file: File, question: string) => void
  isDisabled?: boolean
}

export function InputBar({ onSend, onUpload, isDisabled }: Props) {
  const [text, setText] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || isDisabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, isDisabled, onSend])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const handleUpload = (file: File, question: string) => {
    setShowUpload(false)
    onUpload(file, question)
  }

  return (
    <div className="p-3 md:p-4 border-t border-gray-200 bg-white">
      {showUpload && (
        <div className="mb-3">
          <FileUpload onUpload={handleUpload} onCancel={() => setShowUpload(false)} isDisabled={isDisabled} />
        </div>
      )}

      <div className={cn(
        'flex items-end gap-2 bg-gray-50 border rounded-2xl px-3 py-2 transition-colors',
        isDisabled ? 'border-gray-200' : 'border-gray-300 focus-within:border-brand-400 focus-within:bg-white',
      )}>
        <button
          onClick={() => setShowUpload(v => !v)}
          disabled={isDisabled}
          title="Adjuntar PDF"
          className={cn(
            'p-1.5 rounded-lg transition-colors flex-shrink-0 mb-0.5',
            showUpload ? 'bg-brand-100 text-brand-600' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-200',
            isDisabled && 'opacity-50 cursor-not-allowed',
          )}
        >
          {showUpload ? <X className="w-4 h-4" /> : <Paperclip className="w-4 h-4" />}
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          placeholder={isDisabled ? 'LaborIA está respondiendo…' : '¿Cuál es tu consulta laboral?'}
          rows={1}
          className="flex-1 bg-transparent text-sm resize-none focus:outline-none text-gray-900 placeholder-gray-400 max-h-40 py-1"
        />

        <button
          onClick={handleSend}
          disabled={!text.trim() || isDisabled}
          className="p-1.5 bg-brand-600 text-white rounded-xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0 mb-0.5"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>

      <p className="text-center text-xs text-gray-400 mt-2">
        LaborIA puede cometer errores. Consulta con un abogado para casos complejos.
      </p>
    </div>
  )
}
