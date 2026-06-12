import { useEffect, useState, useCallback } from 'react';
import { useOnboardingStore } from '@/stores/onboardingStore';
import { Button } from '@/components/ui/button';
import { ArrowRight, ArrowLeft, X } from 'lucide-react';

interface TourStep {
  target: string;
  title: string;
  description: string;
  placement: 'top' | 'bottom' | 'left' | 'right';
}

const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="library-add"]',
    title: 'Upload your papers',
    description: 'Click here to upload PDFs, import from a URL, or link to external documents. This is your home base for all research.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="sidebar-projects"]',
    title: 'Organize with Projects',
    description: 'Create projects to group papers by class, research topic, or any system you like. Click the + icon next to Projects.',
    placement: 'right',
  },
  {
    target: '[data-tour="library-search"]',
    title: 'Deep Search',
    description: 'Toggle Deep Search to search the full text of every paper in your library using AI-powered semantic search.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="topbar-settings"]',
    title: 'Settings & AI',
    description: 'Choose your storage provider (Google Drive or GitHub), pick AI models, and manage your OpenRouter API key here.',
    placement: 'bottom',
  },
];

export function OnboardingTour() {
  const { hasSeenTour, tourStep, setTourStep, completeTour } = useOnboardingStore();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  const currentStep = TOUR_STEPS[tourStep];

  const updateTargetRect = useCallback(() => {
    if (!currentStep) return;
    const el = document.querySelector(currentStep.target);
    if (el) {
      setTargetRect(el.getBoundingClientRect());
    } else {
      setTargetRect(null);
    }
  }, [currentStep]);

  useEffect(() => {
    if (hasSeenTour || !currentStep) {
      setIsVisible(false);
      return;
    }

    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      updateTargetRect();
      setIsVisible(true);
    }, 500);

    window.addEventListener('resize', updateTargetRect);
    window.addEventListener('scroll', updateTargetRect, true);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateTargetRect);
      window.removeEventListener('scroll', updateTargetRect, true);
    };
  }, [hasSeenTour, currentStep, updateTargetRect]);

  const handleNext = () => {
    if (tourStep < TOUR_STEPS.length - 1) {
      setTourStep(tourStep + 1);
    } else {
      completeTour();
    }
  };

  const handlePrev = () => {
    if (tourStep > 0) {
      setTourStep(tourStep - 1);
    }
  };

  const handleSkip = () => {
    completeTour();
  };

  if (!isVisible || !currentStep || !targetRect) {
    return null;
  }

  const padding = 8;
  const tooltipWidth = 320;
  const tooltipHeight = 180;

  let tooltipStyle: React.CSSProperties = {};

  switch (currentStep.placement) {
    case 'bottom':
      tooltipStyle = {
        left: Math.min(targetRect.left + targetRect.width / 2 - tooltipWidth / 2, window.innerWidth - tooltipWidth - 16),
        top: targetRect.bottom + padding + 8,
        width: tooltipWidth,
      };
      break;
    case 'top':
      tooltipStyle = {
        left: Math.min(targetRect.left + targetRect.width / 2 - tooltipWidth / 2, window.innerWidth - tooltipWidth - 16),
        top: Math.max(targetRect.top - tooltipHeight - padding, 16),
        width: tooltipWidth,
      };
      break;
    case 'right':
      tooltipStyle = {
        left: targetRect.right + padding,
        top: Math.max(targetRect.top + targetRect.height / 2 - tooltipHeight / 2, 16),
        width: tooltipWidth,
      };
      break;
    case 'left':
      tooltipStyle = {
        left: Math.max(targetRect.left - tooltipWidth - padding, 16),
        top: Math.max(targetRect.top + targetRect.height / 2 - tooltipHeight / 2, 16),
        width: tooltipWidth,
      };
      break;
  }

  return (
    <div className="fixed inset-0 z-[100]" style={{ pointerEvents: 'auto' }}>
      {/* Dark overlay with spotlight cutout */}
      <svg className="absolute inset-0 w-full h-full">
        <defs>
          <mask id="spotlight-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            <rect
              x={targetRect.left - padding}
              y={targetRect.top - padding}
              width={targetRect.width + padding * 2}
              height={targetRect.height + padding * 2}
              rx="8"
              fill="black"
            />
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0,0,0,0.6)"
          mask="url(#spotlight-mask)"
          style={{ pointerEvents: 'auto' }}
          onClick={handleSkip}
        />
      </svg>

      {/* Highlight border around target */}
      <div
        className="absolute rounded-lg border-2 border-primary pointer-events-none"
        style={{
          left: targetRect.left - padding,
          top: targetRect.top - padding,
          width: targetRect.width + padding * 2,
          height: targetRect.height + padding * 2,
        }}
      />

      {/* Tooltip */}
      <div
        className="absolute bg-background rounded-xl border shadow-xl p-4 flex flex-col gap-3 animate-in fade-in zoom-in-95 duration-200"
        style={tooltipStyle}
      >
        <div className="flex items-start justify-between">
          <h3 className="font-semibold text-sm">{currentStep.title}</h3>
          <Button variant="ghost" size="icon" className="h-6 w-6 -mr-2 -mt-2" onClick={handleSkip}>
            <X className="h-3 w-3" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {currentStep.description}
        </p>
        <div className="flex items-center justify-between mt-auto pt-1">
          <div className="flex gap-1">
            {TOUR_STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-colors ${
                  i === tourStep ? 'w-4 bg-primary' : 'w-1.5 bg-muted-foreground/30'
                }`}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {tourStep > 0 && (
              <Button variant="ghost" size="sm" className="h-8" onClick={handlePrev}>
                <ArrowLeft className="h-3 w-3 mr-1" />
                Back
              </Button>
            )}
            <Button size="sm" className="h-8" onClick={handleNext}>
              {tourStep === TOUR_STEPS.length - 1 ? 'Finish' : 'Next'}
              {tourStep < TOUR_STEPS.length - 1 && <ArrowRight className="h-3 w-3 ml-1" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
