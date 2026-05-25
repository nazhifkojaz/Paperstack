import { PdfChatPanelShell } from './PdfChatPanelShell';
import { usePdfChatPanelController } from './usePdfChatPanelController';

interface ChatPanelProps {
  pdfId: string;
  /** Explicit page jumps keep passive scrolling separate from navigation. */
  jumpToPage: (page: number) => void;
}

export const ChatPanel = (props: ChatPanelProps) => {
  const [isOpen, shellProps] = usePdfChatPanelController(props);
  if (!isOpen) return null;

  return <PdfChatPanelShell {...shellProps} />;
};
