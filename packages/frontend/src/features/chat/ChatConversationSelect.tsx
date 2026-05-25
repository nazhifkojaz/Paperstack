import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Conversation } from '@/api/chat';

interface ChatConversationSelectProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
}

export function ChatConversationSelect({
  conversations,
  activeConversationId,
  onSelect,
}: ChatConversationSelectProps) {
  if (conversations.length <= 1) return null;

  return (
    <div className="px-3 py-2 border-b shrink-0">
      <Select value={activeConversationId ?? ''} onValueChange={onSelect}>
        <SelectTrigger className="h-7 text-xs">
          <SelectValue placeholder="Select conversation" />
        </SelectTrigger>
        <SelectContent>
          {conversations.map((conversation, index) => (
            <SelectItem
              key={conversation.id}
              value={conversation.id}
              className="text-xs"
            >
              {conversation.title || `Chat ${index + 1}`}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
