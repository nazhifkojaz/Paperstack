import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useUpdateAnnotation, useDeleteAnnotation } from '@/api/annotations'
import { useAnnotationStore } from '@/stores/annotationStore'
import type { Annotation } from '@/api/annotations'
import { ANNOTATION_COLORS } from './constants'

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
}

export const AnnotationContextMenu = ({
  annotation,
  position,
  onClose,
  onEditNote,
  onExplainThis,
}: AnnotationContextMenuProps) => {
  const menuRef = useRef<HTMLDivElement>(null)
  const { mutate: updateAnnotation } = useUpdateAnnotation()
  const { mutate: deleteAnnotation } = useDeleteAnnotation()
  const { setSelectedAnnotationId } = useAnnotationStore()

  // Calculate clamped position to keep menu within viewport
  const menuPosition = (() => {
    const MENU_WIDTH = 180
    const MENU_HEIGHT = annotation.type === 'highlight' && annotation.selected_text ? 220 : annotation.type === 'highlight' ? 180 : 140
    const PADDING = 8

    let x = position.x
    let y = position.y

    // Clamp horizontally
    if (x + MENU_WIDTH > window.innerWidth - PADDING) {
      x = window.innerWidth - MENU_WIDTH - PADDING
    }
    if (x < PADDING) {
      x = PADDING
    }

    // Clamp vertically
    if (y + MENU_HEIGHT > window.innerHeight - PADDING) {
      y = window.innerHeight - MENU_HEIGHT - PADDING
    }
    if (y < PADDING) {
      y = PADDING
    }

    return { x, y }
  })()

  // Handle click outside
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
    if (onExplainThis) onExplainThis(annotation.id)
    onClose()
  }

  const handleColorChange = (color: string) => {
    updateAnnotation({
      id: annotation.id,
      data: { color },
    })
    onClose()
  }

  const handleCopyText = async () => {
    if (annotation.selected_text) {
      await navigator.clipboard.writeText(annotation.selected_text)
      onClose()
    }
  }

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
        {annotation.note_content ? 'Edit Note' : 'Add Note'}
      </button>

      {/* Explain This (only for highlights with selected text) */}
      {annotation.type === 'highlight' && annotation.selected_text && onExplainThis && (
        <button
          className="w-full px-4 py-2 text-left text-sm text-violet-700 hover:bg-violet-50 flex items-center gap-2"
          onClick={handleExplainThis}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.347a5.001 5.001 0 01-3.011 1.247" />
          </svg>
          Explain This
        </button>
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
          onClick={handleCopyText}
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
