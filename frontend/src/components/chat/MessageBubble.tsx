import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import type { Message } from '@/types'
import { LegalReference } from './LegalReference'
import { AlertCircle } from 'lucide-react'

interface Props { message: Message }

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] md:max-w-[70%] bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
          <div className="markdown-body prose-invert text-sm whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="flex gap-2 max-w-[90%] md:max-w-[80%]">
        {/* Avatar */}
        <div className="flex-shrink-0 w-7 h-7 bg-gradient-to-br from-brand-500 to-brand-700 rounded-full flex items-center justify-center text-white text-xs font-bold shadow-sm mt-1">
          L
        </div>

        <div className="flex-1 min-w-0">
          {/* Content */}
          <div className={cn(
            'bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100',
            message.error && 'border-red-200 bg-red-50',
          )}>
            {message.error && !message.content && (
              <div className="flex items-center gap-2 text-red-600 text-sm">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{message.error}</span>
              </div>
            )}

            {message.content && (
              <div className={cn('markdown-body text-sm text-gray-800', message.isStreaming && 'streaming-cursor')}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )}

            {!message.content && message.isStreaming && (
              <div className="flex items-center gap-1 py-1">
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            )}
          </div>

          {/* Sources */}
          {message.sources && message.sources.length > 0 && (
            <LegalReference sources={message.sources} />
          )}
        </div>
      </div>
    </div>
  )
}
