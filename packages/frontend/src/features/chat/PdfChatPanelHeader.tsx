import {
  Maximize2,
  MessageSquare,
  Minimize2,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Conversation } from '@/api/chat';

interface PdfChatPanelHeaderProps {
  activeConversationId: string | null;
  conversations: Conversation[];
  isFullscreen: boolean;
  onClose: () => void;
  onDeleteConversation: (conversationId: string, title: string) => void;
  onNewConversation: () => void;
  onToggleFullscreen: () => void;
}

export function PdfChatPanelHeader({
  activeConversationId,
  conversations,
  isFullscreen,
  onClose,
  onDeleteConversation,
  onNewConversation,
  onToggleFullscreen,
}: PdfChatPanelHeaderProps) {
  const activeIndex = conversations.findIndex(
    (conversation) => conversation.id === activeConversationId,
  );
  const activeConversation =
    activeIndex >= 0 ? conversations[activeIndex] : undefined;
  const activeTitle = activeConversation?.title || `Chat ${activeIndex + 1}`;

  return (
    <div className="p-4 border-b flex items-center justify-between shrink-0">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-primary" />
        <h2 className="font-semibold">Chat</h2>
      </div>
      <div className="flex items-center gap-1">
        {activeConversationId && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDeleteConversation(activeConversationId, activeTitle)}
            title="Delete conversation"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewConversation}
          title="New conversation"
        >
          <Plus className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleFullscreen}
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        >
          {isFullscreen ? (
            <Minimize2 className="h-4 w-4" />
          ) : (
            <Maximize2 className="h-4 w-4" />
          )}
        </Button>
        <Button variant="ghost" size="icon" onClick={onClose} title="Close chat panel">
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
