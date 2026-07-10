import React, { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAnnotationStore } from '@/stores/annotationStore'
import { useAnnotations, useDeleteAnnotation, Annotation } from '@/api/annotations'
import { useColorLabels, useUpdateColorLabels } from '@/api/colorLabels'
import { useNewPdfViewerStore } from '@/features/pdf-viewer/pdfViewerStore'
import { requestAnnotationRelocation } from '@/features/pdf-viewer/useTextIndexMatcher'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { AlertTriangle, ChevronDown, ChevronRight, Expand, Highlighter, Pencil, RefreshCw, Square, StickyNote, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AnnotationDetailDrawer } from './AnnotationDetailDrawer'
import { DEFAULT_HIGHLIGHT_COLOR, DEFAULT_COLOR_LABELS, ANNOTATION_COLORS } from './constants'

type ColorCount = { color: string; count: number }

type AnnotationGroup = {
  key: string
  label: string
  color?: string
  count: number
  annotations: Annotation[]
  colorCounts?: ColorCount[]
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

function getAnnotationPosition(ann: Annotation): { y: number; x: number } {
  if (!ann.rects || ann.rects.length === 0) return { y: 1, x: 1 }
  const minY = Math.min(...ann.rects.map(r => r.y))
  const rectsInRow = ann.rects.filter(r => r.y === minY)
  const minX = rectsInRow.length > 0 ? Math.min(...rectsInRow.map(r => r.x)) : Math.min(...ann.rects.map(r => r.x))
  return { y: minY, x: minX }
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
    .map(([page, annotations]) => {
      const colorMap = new Map<string, number>()
      for (const ann of annotations) {
        const color = ann.color || DEFAULT_HIGHLIGHT_COLOR
        colorMap.set(color, (colorMap.get(color) ?? 0) + 1)
      }
      const colorCounts: ColorCount[] = Array.from(colorMap.entries())
        .map(([color, count]) => ({ color, count }))
        .sort((a, b) => {
          const ai = COLOR_ORDER.indexOf(a.color)
          const bi = COLOR_ORDER.indexOf(b.color)
          return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
        })

      return {
        key: `page-${page}`,
        label: `Page ${page}`,
        count: annotations.length,
        annotations: annotations.sort((a, b) => {
          const pa = getAnnotationPosition(a)
          const pb = getAnnotationPosition(b)
          return pa.y !== pb.y ? pa.y - pb.y : pa.x - pb.x
        }),
        colorCounts,
      }
    })
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))
}

const COLOR_ORDER = ANNOTATION_COLORS.map(c => c.color)

function groupAnnotationsByColor(annotations: Annotation[], labels: Record<string, string>): AnnotationGroup[] {
  const grouped = new Map<string, Annotation[]>()

  for (const ann of annotations) {
    const color = ann.color || DEFAULT_HIGHLIGHT_COLOR
    if (!grouped.has(color)) {
      grouped.set(color, [])
    }
    grouped.get(color)!.push(ann)
  }

  return Array.from(grouped.entries())
    .map(([color, annotations]) => ({
      key: `color-${color}`,
      label: labels[color] || color,
      color,
      count: annotations.length,
      annotations: annotations.sort((a, b) => {
        if (a.page_number !== b.page_number) return a.page_number - b.page_number
        const pa = getAnnotationPosition(a)
        const pb = getAnnotationPosition(b)
        return pa.y !== pb.y ? pa.y - pb.y : pa.x - pb.x
      }),
    }))
    .sort((a, b) => {
      const ai = COLOR_ORDER.indexOf(a.color)
      const bi = COLOR_ORDER.indexOf(b.color)
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
    })
}

const ColorGroupLabel: React.FC<{ color: string; label: string }> = ({ color, label }) => {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(label)
  const { mutate: updateLabels } = useUpdateColorLabels()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const handleSave = useCallback(() => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== label) {
      updateLabels({ labels: { [color]: trimmed } })
    }
    setEditing(false)
  }, [draft, label, color, updateLabels])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSave()
    } else if (e.key === 'Escape') {
      setDraft(label)
      setEditing(false)
    }
  }, [handleSave, label])

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className="flex-1 text-left bg-white border border-gray-300 rounded px-1 py-0 text-[10px] font-semibold uppercase tracking-wide text-foreground outline-none min-w-0"
      />
    )
  }

  return (
    <button
      type="button"
      className="flex-1 text-left flex items-center gap-0.5 group/label"
      onClick={(e) => {
        e.stopPropagation()
        setDraft(label)
        setEditing(true)
      }}
    >
      <span>{label}</span>
      <Pencil className="h-2.5 w-2.5 opacity-0 group-hover/label:opacity-50 transition-opacity" />
    </button>
  )
}

interface SetAnnotationListProps {
  setId: string
  pdfId?: string
  groupBy: 'page' | 'color'
}

export const SetAnnotationList: React.FC<SetAnnotationListProps> = ({ setId, pdfId, groupBy }) => {
  const selectedAnnotationId = useAnnotationStore(s => s.selectedAnnotationId)
  const { data: annotations = [], isLoading } = useAnnotations(setId)
  const { mutate: deleteAnnotation, isPending: isDeletingAnnotation } = useDeleteAnnotation()
  const { data: colorLabels = DEFAULT_COLOR_LABELS } = useColorLabels()
  const queryClient = useQueryClient()
  const jumpToPage = useNewPdfViewerStore((state) => state.jumpToPage)
  const setSelectedAnnotationId = useAnnotationStore((state) => state.setSelectedAnnotationId)
  const setSelectedSetId = useAnnotationStore((state) => state.setSelectedSetId)

  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set())
  const [deletingAnnotation, setDeletingAnnotation] = useState<Annotation | null>(null)
  const [detailAnnotationId, setDetailAnnotationId] = useState<string | null>(null)

  const detailAnnotation = annotations.find(annotation => annotation.id === detailAnnotationId) ?? null

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
    jumpToPage(annotation.page_number)
    setSelectedAnnotationId(annotation.id)
  }

  const handleRetryLocate = (annotation: Annotation) => {
    setSelectedSetId(setId)
    setSelectedAnnotationId(annotation.id)
    requestAnnotationRelocation(annotation.id)
    jumpToPage(annotation.page_number)
    queryClient.invalidateQueries({ queryKey: ['annotations', setId] })
    toast.info('Retrying PDF location.')
  }

  const handleDeleteAnnotation = () => {
    if (!deletingAnnotation) return
    deleteAnnotation(
      {
        id: deletingAnnotation.id,
        setId: deletingAnnotation.set_id,
      },
      {
        onSuccess: () => {
          if (selectedAnnotationId === deletingAnnotation.id) {
            setSelectedAnnotationId(null)
          }
          if (detailAnnotationId === deletingAnnotation.id) {
            setDetailAnnotationId(null)
          }
          setDeletingAnnotation(null)
          toast.success('Annotation deleted.')
        },
      },
    )
  }

  const groupedAnnotations: AnnotationGroup[] = React.useMemo(() => {
    if (groupBy === 'color') {
      return groupAnnotationsByColor(annotations, colorLabels)
    }
    return groupAnnotationsByPage(annotations)
  }, [annotations, groupBy, colorLabels])

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
    <>
      <div className="pb-1">
      {groupedAnnotations.map((group) => {
        const isCollapsed = collapsedKeys.has(group.key)

        return (
          <div key={group.key} className="mb-2 last:mb-0">
            <div
              className="w-full flex items-center gap-1 px-4 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide hover:bg-muted/40 rounded-md transition-colors"
            >
              <button
                type="button"
                onClick={() => toggleGroup(group.key)}
                className={cn(
                  'flex items-center gap-1 text-left min-w-0',
                  groupBy === 'color' ? 'shrink-0' : 'flex-1',
                )}
                aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${group.label}`}
              >
                {isCollapsed ? (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                )}
                {group.color && (
                  <span
                    className="shrink-0 w-2 h-2 rounded-full inline-block"
                    style={{ backgroundColor: group.color }}
                  />
                )}
                {groupBy !== 'color' && (
                  <span className="flex-1 text-left">{group.label}</span>
                )}
              </button>
              {groupBy === 'color' && group.color && (
                <ColorGroupLabel color={group.color} label={group.label} />
              )}
              {groupBy === 'page' && (group.colorCounts?.length ?? 0) > 0 && (
                <div className="flex items-center gap-1 shrink-0 normal-case tracking-normal">
                  {group.colorCounts?.map(({ color, count }) => {
                    const colorLabel = colorLabels[color] || color
                    return (
                      <span
                        key={color}
                        className="flex items-center gap-0.5"
                        title={`${colorLabel}: ${count}`}
                      >
                        <span
                          className="w-2 h-2 rounded-full inline-block"
                          style={{ backgroundColor: color }}
                        />
                        <span>{count}</span>
                      </span>
                    )
                  })}
                </div>
              )}
              <span className="text-[9px] bg-muted px-1.5 py-0.5 rounded-full shrink-0">
                {group.count}
              </span>
            </div>

            {!isCollapsed && (
              <div className="space-y-1 px-1 mt-1">
                {group.annotations.map((annotation) => {
                  const isSelected = annotation.id === selectedAnnotationId
                  const preview = getAnnotationPreview(annotation)
                  const typeIcon = TYPE_ICONS[annotation.type]
                  const isUnlocated = annotation.rects.length === 0 && !!annotation.selected_text

                  return (
                    <div
                      key={annotation.id}
                      data-annotation-id={annotation.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleAnnotationClick(annotation)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          handleAnnotationClick(annotation)
                        }
                      }}
                      className={cn(
                        'group w-full text-left px-3 py-2 rounded-md text-sm flex items-start gap-2 transition-colors',
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
                        {groupBy === 'color' && !isUnlocated && (
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
                      <div className="ml-1 flex shrink-0 items-center gap-0.5">
                        {isUnlocated && (
                          <button
                            type="button"
                            aria-label="Retry locating annotation"
                            title="Retry locating annotation"
                            className="flex h-7 w-7 items-center justify-center rounded-md text-amber-600 hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                            onClick={(event) => {
                              event.stopPropagation()
                              handleRetryLocate(annotation)
                            }}
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          aria-label="Open annotation details"
                          title="Open annotation details"
                          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          onClick={(event) => {
                            event.stopPropagation()
                            setDetailAnnotationId(annotation.id)
                          }}
                        >
                          <Expand className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          aria-label="Delete annotation"
                          title="Delete annotation"
                          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          onClick={(event) => {
                            event.stopPropagation()
                            setDeletingAnnotation(annotation)
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
      </div>

      <AnnotationDetailDrawer
        annotation={detailAnnotation}
        pdfId={pdfId}
        open={!!detailAnnotation}
        onOpenChange={(open) => {
          if (!open) setDetailAnnotationId(null)
        }}
      />

      <Dialog
        open={!!deletingAnnotation}
        onOpenChange={(open) => {
          if (!open) setDeletingAnnotation(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete annotation</DialogTitle>
            <DialogDescription>
              This will permanently delete the annotation on page {deletingAnnotation?.page_number}.
            </DialogDescription>
          </DialogHeader>
          {deletingAnnotation && (
            <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
              {getAnnotationPreview(deletingAnnotation)}
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={() => setDeletingAnnotation(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteAnnotation}
              disabled={isDeletingAnnotation}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
