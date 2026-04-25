import React, { useState, useCallback } from 'react'
import { useAnnotationStore } from '@/stores/annotationStore'
import { useAnnotations, Annotation } from '@/api/annotations'
import { usePdfViewerStore } from '@/stores/pdfViewerStore'
import { AlertTriangle, Highlighter, Square, StickyNote, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

type AnnotationGroup = {
  key: string
  label: string
  count: number
  annotations: Annotation[]
}

const TYPE_LABELS: Record<Annotation['type'], string> = {
  highlight: 'Highlights',
  rect: 'Rectangles',
  note: 'Notes',
}

const TYPE_ICONS: Record<Annotation['type'], React.ReactNode> = {
  highlight: <Highlighter className="h-3.5 w-3.5" />,
  rect: <Square className="h-3.5 w-3.5" />,
  note: <StickyNote className="h-3.5 w-3.5" />,
}

const FALLBACK_LABELS: Record<Annotation['type'], string> = {
  highlight: 'Highlight',
  rect: 'Rectangle',
  note: 'Note',
}

function getAnnotationPreview(annotation: Annotation): string {
  if (annotation.type === 'highlight' && annotation.selected_text) {
    return annotation.selected_text
  }
  if (annotation.type === 'note' && annotation.note_content) {
    return annotation.note_content
  }
  return FALLBACK_LABELS[annotation.type]
}

function groupAnnotationsByPage(annotations: Annotation[]): AnnotationGroup[] {
  const grouped = new Map<number, Annotation[]>()

  for (const ann of annotations) {
    const page = ann.page_number
    if (!grouped.has(page)) {
      grouped.set(page, [])
    }
    grouped.get(page)!.push(ann)
  }

  return Array.from(grouped.entries())
    .map(([page, annotations]) => ({
      key: `page-${page}`,
      label: `Page ${page}`,
      count: annotations.length,
      annotations: annotations.sort((a, b) => a.id.localeCompare(b.id)),
    }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))
}

function groupAnnotationsByType(annotations: Annotation[]): AnnotationGroup[] {
  const grouped = new Map<Annotation['type'], Annotation[]>()

  for (const ann of annotations) {
    const type = ann.type
    if (!grouped.has(type)) {
      grouped.set(type, [])
    }
    grouped.get(type)!.push(ann)
  }

  return Array.from(grouped.entries())
    .map(([type, annotations]) => ({
      key: `type-${type}`,
      label: TYPE_LABELS[type],
      count: annotations.length,
      annotations: annotations.sort((a, b) => a.id.localeCompare(b.id)),
    }))
    .sort((a, b) => a.label.localeCompare(b.label))
}

interface SetAnnotationListProps {
  setId: string
  groupBy: 'page' | 'type'
}

export const SetAnnotationList: React.FC<SetAnnotationListProps> = ({ setId, groupBy }) => {
  const selectedAnnotationId = useAnnotationStore(s => s.selectedAnnotationId)
  const { data: annotations = [], isLoading } = useAnnotations(setId)
  const setCurrentPage = usePdfViewerStore((state) => state.setCurrentPage)
  const setSelectedAnnotationId = useAnnotationStore((state) => state.setSelectedAnnotationId)
  const setSelectedSetId = useAnnotationStore((state) => state.setSelectedSetId)

  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set())

  const toggleGroup = useCallback((key: string) => {
    setCollapsedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }, [])

  const handleAnnotationClick = (annotation: Annotation) => {
    setSelectedSetId(setId)
    setCurrentPage(annotation.page_number)
    setSelectedAnnotationId(annotation.id)
  }

  const groupedAnnotations: AnnotationGroup[] = React.useMemo(() => {
    if (groupBy === 'type') {
      return groupAnnotationsByType(annotations)
    }
    return groupAnnotationsByPage(annotations)
  }, [annotations, groupBy])

  if (isLoading) {
    return (
      <div className="px-3 py-2 space-y-2">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse">
            <div className="h-8 bg-muted rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (annotations.length === 0) {
    return (
      <div className="px-3 py-3">
        <p className="text-xs text-muted-foreground">No annotations yet.</p>
      </div>
    )
  }

  return (
    <div className="pb-1">
      {groupedAnnotations.map((group) => {
        const isCollapsed = collapsedKeys.has(group.key)

        return (
          <div key={group.key} className="mb-2 last:mb-0">
            <button
              onClick={() => toggleGroup(group.key)}
              className="w-full flex items-center gap-1 px-4 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide hover:bg-muted/40 rounded-md transition-colors"
            >
              {isCollapsed ? (
                <ChevronRight className="h-3 w-3 shrink-0" />
              ) : (
                <ChevronDown className="h-3 w-3 shrink-0" />
              )}
              <span className="flex-1 text-left">{group.label}</span>
              <span className="text-[9px] bg-muted px-1.5 py-0.5 rounded-full shrink-0">
                {group.count}
              </span>
            </button>

            {!isCollapsed && (
              <div className="space-y-1 px-1 mt-1">
                {group.annotations.map((annotation) => {
                  const isSelected = annotation.id === selectedAnnotationId
                  const preview = getAnnotationPreview(annotation)
                  const typeIcon = TYPE_ICONS[annotation.type]
                  const isUnlocated = annotation.rects.length === 0 && !!annotation.selected_text

                  return (
                    <button
                      key={annotation.id}
                      data-annotation-id={annotation.id}
                      onClick={() => handleAnnotationClick(annotation)}
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-md text-sm flex items-start gap-2 transition-colors',
                        isSelected
                          ? 'bg-primary/10 border border-primary/20'
                          : 'hover:bg-muted/50'
                      )}
                    >
                      <div className="shrink-0 mt-0.5">
                        {typeIcon}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className={cn(
                          'text-xs break-words leading-relaxed',
                          isSelected ? 'text-foreground font-medium' : 'text-muted-foreground'
                        )}>
                          {preview}
                        </p>
                        {isUnlocated && (
                          <span className="text-[10px] text-amber-500 flex items-center gap-0.5 mt-0.5">
                            <AlertTriangle className="h-2.5 w-2.5" />
                            Could not locate in PDF
                          </span>
                        )}
                        {groupBy === 'type' && !isUnlocated && (
                          <span className="text-[10px] text-muted-foreground mt-0.5 block">
                            Page {annotation.page_number}
                          </span>
                        )}
                      </div>
                      {annotation.color && (
                        <div
                          className="shrink-0 w-2 h-2 rounded-full mt-1"
                          style={{ backgroundColor: annotation.color }}
                        />
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
