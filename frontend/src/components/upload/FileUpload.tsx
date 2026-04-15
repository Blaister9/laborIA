import { useCallback, useState, useRef } from 'react'
import { Upload, X, FileText, Send } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  onUpload: (file: File, question: string) => void
  onCancel: () => void
  isDisabled?: boolean
}

export function FileUpload({ onUpload, onCancel, isDisabled }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [question, setQuestion] = useState('Analiza este documento e identifica sus implicaciones legales laborales.')
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f?.type === 'application/pdf') setFile(f)
  }, [])

  const handleSubmit = () => {
    if (file && question.trim()) onUpload(file, question)
  }

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3 shadow-sm">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => !file && inputRef.current?.click()}
        className={cn(
          'border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors',
          isDragging ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-brand-400 hover:bg-gray-50',
          file && 'cursor-default',
        )}
      >
        <input ref={inputRef} type="file" accept=".pdf" className="hidden"
          onChange={e => setFile(e.target.files?.[0] ?? null)} />

        {file ? (
          <div className="flex items-center gap-2 justify-center">
            <FileText className="w-5 h-5 text-brand-600" />
            <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]">{file.name}</span>
            <span className="text-xs text-gray-400">({(file.size / 1024).toFixed(0)} KB)</span>
            <button onClick={e => { e.stopPropagation(); setFile(null) }}
              className="text-gray-400 hover:text-red-500 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div>
            <Upload className="w-6 h-6 text-gray-400 mx-auto mb-1" />
            <p className="text-sm text-gray-500">
              Arrastra un PDF o <span className="text-brand-600 font-medium">haz clic para seleccionar</span>
            </p>
            <p className="text-xs text-gray-400 mt-0.5">Solo PDF, máx. 10 MB</p>
          </div>
        )}
      </div>

      {/* Question */}
      <textarea
        value={question}
        onChange={e => setQuestion(e.target.value)}
        placeholder="¿Qué quieres saber sobre este documento?"
        rows={2}
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400"
      />

      {/* Actions */}
      <div className="flex gap-2">
        <button onClick={onCancel}
          className="flex-1 py-1.5 text-sm text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
          Cancelar
        </button>
        <button
          onClick={handleSubmit}
          disabled={!file || !question.trim() || isDisabled}
          className="flex-1 py-1.5 text-sm text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5 transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          Analizar
        </button>
      </div>
    </div>
  )
}
