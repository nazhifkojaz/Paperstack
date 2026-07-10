import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { RefreshCw, Sparkles, MessageCircle } from 'lucide-react'
import { useUpdateAnnotation, useDeleteAnnotation } from '@/api/annotations'
import { useAnnotationStore } from '@/stores/annotationStore'
import type { Annotation } from '@/api/annotations'
import { useClipboard } from '@/hooks/useClipboard'
import { ANNOTATION_COLORS } from './constants'
import { getAnnotationUserNote } from './annotationContent'

interface Position {
  x: number
  y: number
}

interface AnnotationContextMenuProps {
  annotation: Annotation
  position: Position
  onClose: () => void
  onEditNote: (annotationId: string) => void
  onExplainThis?: (annotationId: string) => void
  onParaphraseThis?: (annotationId: string) => void
  onAskInChat?: (annotationId: string) => void
  aiUsesRemaining?: number | null
}

export const AnnotationContextMenu = ({
  annotation,
  position,
  onClose,
  onEditNote,
  onExplainThis,
  onParaphraseThis,
  onAskInChat,
  aiUsesRemaining,
}: AnnotationContextMenuProps) => {
  const menuRef = useRef<HTMLDivElement>(null)
  const { mutate: updateAnnotation } = useUpdateAnnotation()
  const { mutate: deleteAnnotation } = useDeleteAnnotation()
  const setSelectedAnnotationId = useAnnotationStore(s => s.setSelectedAnnotationId)
  const hasUserNote = !!getAnnotationUserNote(annotation)
  const isHighlight = annotation.type === 'highlight'
  const hasSelectedText = !!annotation.selected_text
  const canShowExplain = isHighlight && !!onExplainThis
  const canShowParaphrase = isHighlight && !!onParaphraseThis
  const canShowAskInChat = isHighlight && !!onAskInChat
  const canUseAiActions = hasSelectedText
  const aiUnavailableTitle = canUseAiActions
    ? undefined
    : 'No selected text for this annotation'
  const showAiQuota = canUseAiActions
    && (canShowExplain || canShowParaphrase)
    && aiUsesRemaining !== null
    && aiUsesRemaining !== undefined
    && aiUsesRemaining >= 0

  const menuPosition = (() => {
    const MENU_WIDTH = 180
    const MENU_HEIGHT = 140
      + (isHighlight && hasSelectedText ? 40 : 0)
      + (canShowExplain ? 40 : 0)
      + (canShowParaphrase ? 40 : 0)
      + (canShowAskInChat ? 40 : 0)
      + (showAiQuota ? 18 : 0)
    const PADDING = 8

    let x = position.x
    let y = position.y

    if (x + MENU_WIDTH > window.innerWidth - PADDING) {
      x = window.innerWidth - MENU_WIDTH - PADDING
    }
    if (x < PADDING) {
      x = PADDING
    }

    if (y + MENU_HEIGHT > window.innerHeight - PADDING) {
      y = window.innerHeight - MENU_HEIGHT - PADDING
    }
    if (y < PADDING) {
      y = PADDING
    }

    return { x, y }
  })()

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    const handleScroll = () => {
      onClose()
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    document.addEventListener('scroll', handleScroll, true)
    window.addEventListener('resize', onClose)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
      document.removeEventListener('scroll', handleScroll, true)
      window.removeEventListener('resize', onClose)
    }
  }, [onClose])

  const handleEditNote = () => {
    onEditNote(annotation.id)
    onClose()
  }

  const handleExplainThis = () => {
    if (!canUseAiActions) return
    if (onExplainThis) onExplainThis(annotation.id)
    onClose()
  }

  const handleParaphraseThis = () => {
    if (!canUseAiActions) return
    if (onParaphraseThis) onParaphraseThis(annotation.id)
    onClose()
  }

  const handleAskInChat = () => {
    if (!canUseAiActions) return
    if (onAskInChat) onAskInChat(annotation.id)
    onClose()
  }

  const handleColorChange = (color: string) => {
    updateAnnotation({
      id: annotation.id,
      data: { color },
    })
    onClose()
  }

  const { copyToClipboard } = useClipboard({ onSuccess: onClose })

  const handleDelete = () => {
    deleteAnnotation({
      id: annotation.id,
      setId: annotation.set_id,
    })
    setSelectedAnnotationId(null)
    onClose()
  }

  const menu = (
    <div
      ref={menuRef}
      className="fixed bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-[9999] min-w-[180px]"
      style={{
        left: `${menuPosition.x}px`,
        top: `${menuPosition.y}px`,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Add/Edit Note */}
      <button
        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
        onClick={handleEditNote}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        {hasUserNote ? 'Edit Note' : 'Add Note'}
      </button>

      {/* AI actions are visible for highlights; selected text is required to run them. */}
      {canShowExplain && (
        <button
          className="w-full px-4 py-2 text-left text-sm text-violet-700 hover:bg-violet-50 flex items-center gap-2 disabled:cursor-not-allowed disabled:text-violet-300 disabled:hover:bg-transparent"
          onClick={handleExplainThis}
          disabled={!canUseAiActions}
          title={aiUnavailableTitle}
        >
          <Sparkles className="w-4 h-4" />
          Explain This
        </button>
      )}
      {canShowParaphrase && (
        <button
          className="w-full px-4 py-2 text-left text-sm text-violet-700 hover:bg-violet-50 flex items-center gap-2 disabled:cursor-not-allowed disabled:text-violet-300 disabled:hover:bg-transparent"
          onClick={handleParaphraseThis}
          disabled={!canUseAiActions}
          title={aiUnavailableTitle}
        >
          <RefreshCw className="w-4 h-4" />
          Paraphrase This
        </button>
      )}
      {canShowAskInChat && (
        <button
          className="w-full px-4 py-2 text-left text-sm text-violet-700 hover:bg-violet-50 flex items-center gap-2 disabled:cursor-not-allowed disabled:text-violet-300 disabled:hover:bg-transparent"
          onClick={handleAskInChat}
          disabled={!canUseAiActions}
          title={aiUnavailableTitle}
        >
          <MessageCircle className="w-4 h-4" />
          Ask in Chat
        </button>
      )}
      {showAiQuota && (
        <p className="px-4 pb-1 text-[11px] text-gray-500">
          {aiUsesRemaining} AI use{aiUsesRemaining !== 1 ? 's' : ''} remaining
        </p>
      )}

      {/* Change Color */}
      <div className="px-4 py-2">
        <div className="text-xs text-gray-500 mb-1">Color</div>
        <div className="flex gap-1 flex-wrap">
          {ANNOTATION_COLORS.map(({ color }) => (
            <button
              key={color}
              className="w-5 h-5 rounded border border-gray-300 hover:scale-110 transition-transform"
              style={{ backgroundColor: color }}
              onClick={() => handleColorChange(color)}
              aria-label={`Change color to ${color}`}
            />
          ))}
        </div>
      </div>

      {/* Copy Text (only for highlights with selected_text) */}
      {annotation.type === 'highlight' && annotation.selected_text && (
        <button
          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
          onClick={() => { if (annotation.selected_text) copyToClipboard(annotation.selected_text) }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Copy Text
        </button>
      )}

      {/* Delete */}
      <hr className="my-1 border-gray-200" />
      <button
        className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
        onClick={handleDelete}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        Delete
      </button>
    </div>
  )

  return createPortal(menu, document.body)
}
