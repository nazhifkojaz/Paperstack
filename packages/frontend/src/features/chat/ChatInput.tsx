import type { KeyboardEvent, RefObject } from 'react';
import { useEffect, useRef } from 'react';
import { Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface ChatInputProps {
  input: string;
  setInput: (value: string) => void;
  isSending: boolean;
  onSend: () => void;
  onStop: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  placeholder: string;
  disabled?: boolean;
  wrapperClassName?: string;
  innerClassName?: string;
  textareaClassName?: string;
  buttonClassName?: string;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}

export function ChatInput({
  input,
  setInput,
  isSending,
  onSend,
  onStop,
  onKeyDown,
  placeholder,
  disabled = false,
  wrapperClassName = '',
  innerClassName = '',
  textareaClassName = 'min-h-[60px] max-h-[40vh]',
  buttonClassName = '',
  inputRef,
}: ChatInputProps) {
  const fallbackRef = useRef<HTMLTextAreaElement | null>(null);
  const textareaRef = inputRef ?? fallbackRef;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [input, textareaRef]);

  return (
    <div className={`shrink-0 border-t ${wrapperClassName}`}>
      <div className={`flex gap-2 items-end p-3 ${innerClassName}`}>
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className={`resize-none text-sm ${textareaClassName}`}
        />
        {isSending ? (
          <Button
            size="icon"
            onClick={onStop}
            variant="destructive"
            className={`shrink-0 ${buttonClassName}`}
            title="Stop generating"
          >
            <Square className="h-4 w-4 fill-current" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={onSend}
            disabled={!input.trim() || disabled}
            className={`shrink-0 ${buttonClassName}`}
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
