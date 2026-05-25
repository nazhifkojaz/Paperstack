import { ArrowLeft, Loader2, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Conversation } from '@/api/chat';

interface CollectionChatSidebarProps {
  activeConversationId: string | null;
  conversations: Conversation[];
  isCreatingConversation: boolean;
  isLoadingConversations: boolean;
  onBack: () => void;
  onDeleteConversation: (conversationId: string, title: string) => void;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}

export function CollectionChatSidebar({
  activeConversationId,
  conversations,
  isCreatingConversation,
  isLoadingConversations,
  onBack,
  onDeleteConversation,
  onNewConversation,
  onSelectConversation,
}: CollectionChatSidebarProps) {
  return (
    <div className="w-64 border-r flex flex-col shrink-0">
      <div className="p-4 border-b flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={onBack} title="Back to library">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h2 className="font-semibold text-sm truncate flex-1">Collection Chat</h2>
      </div>
      <div className="p-2 border-b">
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-2"
          onClick={onNewConversation}
          disabled={isCreatingConversation}
        >
          <Plus className="h-4 w-4" />
          New conversation
        </Button>
      </div>
      <ScrollArea className="flex-1">
        {isLoadingConversations ? (
          <div className="flex justify-center p-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center p-4">
            No conversations yet.
          </p>
        ) : (
          <div className="p-2 flex flex-col gap-1 overflow-hidden">
            {conversations.map((conversation, index) => {
              const title = conversation.title || `Chat ${index + 1}`;
              const displayTitle =
                title.length > 28 ? `${title.slice(0, 28)}...` : title;
              return (
                <div
                  key={conversation.id}
                  className={`w-full flex items-center gap-1 rounded-md px-2 py-1.5 cursor-pointer transition-colors ${
                    conversation.id === activeConversationId
                      ? 'bg-primary/10 text-primary'
                      : 'hover:bg-muted text-muted-foreground'
                  }`}
                  onClick={() => onSelectConversation(conversation.id)}
                >
                  <span className="text-xs flex-1 min-w-0" title={title}>
                    {displayTitle}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteConversation(conversation.id, title);
                    }}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
