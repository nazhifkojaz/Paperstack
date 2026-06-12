import { useEffect, useState } from 'react';
import { useOnboardingStore } from '@/stores/onboardingStore';
import { Button } from '@/components/ui/button';
import { Wand2, X } from 'lucide-react';

export function AnnotationTooltip() {
  const { hasSeenAnnotationTooltip, markAnnotationTooltipSeen } = useOnboardingStore();
  const [isVisible, setIsVisible] = useState(false);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (hasSeenAnnotationTooltip) return;

    const timer = setTimeout(() => {
      const el = document.querySelector('[data-tour="auto-highlight"]');
      if (el) {
        setTargetRect(el.getBoundingClientRect());
        setIsVisible(true);
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, [hasSeenAnnotationTooltip]);

  const handleDismiss = () => {
    setIsVisible(false);
    markAnnotationTooltipSeen();
  };

  if (!isVisible || !targetRect) return null;

  return (
    <div className="fixed inset-0 z-[90] pointer-events-none">
      {/* Tooltip pointing to auto-highlight button */}
      <div
        className="absolute pointer-events-auto bg-background rounded-xl border shadow-xl p-4 w-72 animate-in fade-in slide-in-from-bottom-2 duration-300"
        style={{
          left: Math.min(targetRect.left, window.innerWidth - 300),
          top: targetRect.bottom + 12,
        }}
      >
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <Wand2 className="h-4 w-4 text-purple-500" />
            <h3 className="font-semibold text-sm">AI Auto-Highlight</h3>
          </div>
          <Button variant="ghost" size="icon" className="h-6 w-6 -mr-2 -mt-2" onClick={handleDismiss}>
            <X className="h-3 w-3" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed mb-3">
          Click this button to automatically extract key findings, methods, definitions, and limitations from your paper.
        </p>
        <Button size="sm" className="w-full" onClick={handleDismiss}>
          Got it
        </Button>
      </div>
    </div>
  );
}
