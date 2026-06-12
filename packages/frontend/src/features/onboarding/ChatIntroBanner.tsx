import { useEffect, useState } from 'react';
import { useOnboardingStore } from '@/stores/onboardingStore';
import { Button } from '@/components/ui/button';
import { MessageSquare, X } from 'lucide-react';

export function ChatIntroBanner() {
  const { hasSeenChatIntro, markChatIntroSeen } = useOnboardingStore();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!hasSeenChatIntro) {
      const timer = setTimeout(() => setVisible(true), 500);
      return () => clearTimeout(timer);
    }
  }, [hasSeenChatIntro]);

  const handleDismiss = () => {
    setVisible(false);
    markChatIntroSeen();
  };

  if (!visible) return null;

  return (
    <div className="bg-primary/5 border-b border-primary/20 p-3 flex items-start gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
      <MessageSquare className="h-4 w-4 text-primary shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">Chat with your paper</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Ask questions about this paper and Paperstack will search the full text and cite the page numbers for you.
        </p>
      </div>
      <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0 -mr-1 -mt-1" onClick={handleDismiss}>
        <X className="h-3 w-3" />
      </Button>
    </div>
  );
}
