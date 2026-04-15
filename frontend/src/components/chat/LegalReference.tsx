import { useState } from 'react'
import { ChevronDown, ChevronUp, BookOpen, AlertTriangle, Info } from 'lucide-react'
import type { ArticleSource } from '@/types'
import { cn } from '@/lib/utils'

interface Props { sources: ArticleSource[] }

export function LegalReference({ sources }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [openArt, setOpenArt] = useState<string | null>(null)

  if (!sources.length) return null

  return (
    <div className="mt-3 border border-gray-200 rounded-lg overflow-hidden text-sm">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <BookOpen className="w-4 h-4 text-brand-600 flex-shrink-0" />
        <span className="font-medium text-gray-700">
          Artículos consultados ({sources.length})
        </span>
        <div className="ml-auto flex gap-1">
          {sources.slice(0, 4).map(s => (
            <SourceChip key={s.chunk_id} source={s} />
          ))}
          {sources.length > 4 && (
            <span className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full text-xs">
              +{sources.length - 4}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />}
      </button>

      {expanded && (
        <div className="divide-y divide-gray-100">
          {sources.map(src => (
            <ArticleCard
              key={src.chunk_id}
              source={src}
              isOpen={openArt === src.chunk_id}
              onToggle={() => setOpenArt(o => o === src.chunk_id ? null : src.chunk_id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SourceChip({ source }: { source: ArticleSource }) {
  const isDerogated = source.derogated
  const isModified = !isDerogated && !!source.modified_by
  return (
    <span className={cn(
      'px-2 py-0.5 rounded-full text-xs font-medium',
      isDerogated ? 'bg-red-100 text-red-700' :
      isModified ? 'bg-yellow-100 text-yellow-700' :
      'bg-brand-50 text-brand-700',
    )}>
      Art. {source.article_number} {source.source !== 'CST' ? source.source : ''}
    </span>
  )
}

function ArticleCard({ source, isOpen, onToggle }: { source: ArticleSource; isOpen: boolean; onToggle: () => void }) {
  const isDerogated = source.derogated
  const isModified = !isDerogated && !!source.modified_by
  const isLey2466 = source.source !== 'CST'

  return (
    <div className={cn('transition-colors', isOpen ? 'bg-gray-50' : 'hover:bg-gray-50/50')}>
      <button onClick={onToggle} className="w-full flex items-start gap-2 px-3 py-2 text-left">
        {isDerogated && <AlertTriangle className="w-3.5 h-3.5 text-red-500 mt-0.5 flex-shrink-0" />}
        {isModified && <Info className="w-3.5 h-3.5 text-yellow-500 mt-0.5 flex-shrink-0" />}
        {!isDerogated && !isModified && <BookOpen className="w-3.5 h-3.5 text-brand-500 mt-0.5 flex-shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn(
              'font-semibold text-xs',
              isDerogated ? 'text-red-700' : isModified ? 'text-yellow-700' : isLey2466 ? 'text-purple-700' : 'text-brand-700',
            )}>
              Art. {source.article_number} {source.source}
            </span>
            {isDerogated && <span className="text-xs bg-red-100 text-red-600 px-1.5 rounded">DEROGADO</span>}
            {isModified && <span className="text-xs bg-yellow-100 text-yellow-600 px-1.5 rounded">MODIFICADO</span>}
            {isLey2466 && <span className="text-xs bg-purple-100 text-purple-600 px-1.5 rounded">LEY 2466/2025</span>}
          </div>
          {source.article_title && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{source.article_title}</p>
          )}
          {isModified && source.modified_by && (
            <p className="text-xs text-yellow-600 mt-0.5">Modificado: {source.modified_by}</p>
          )}
        </div>
        {isOpen ? <ChevronUp className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" />}
      </button>
      {isOpen && (
        <div className="px-3 pb-3">
          <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap border-l-2 border-brand-200 pl-2">
            {source.text.slice(0, 800)}{source.text.length > 800 ? '…' : ''}
          </p>
        </div>
      )}
    </div>
  )
}
