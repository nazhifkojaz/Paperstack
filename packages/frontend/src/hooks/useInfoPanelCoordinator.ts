import { useCitationStore } from '@/stores/citationStore';
import { useChatStore } from '@/stores/chatStore';
import { useSummaryStore } from '@/stores/summaryStore';

export type InfoPanelName = 'citation' | 'chat' | 'summary';

export function useInfoPanelCoordinator() {
    const isCitationPanelOpen = useCitationStore((s) => s.isCitationPanelOpen);
    const isChatPanelOpen = useChatStore((s) => s.isChatPanelOpen);
    const isSummaryPanelOpen = useSummaryStore((s) => s.isSummaryPanelOpen);

    const setCitationPanelOpen = useCitationStore((s) => s.setCitationPanelOpen);
    const setChatPanelOpen = useChatStore((s) => s.setChatPanelOpen);
    const setSummaryPanelOpen = useSummaryStore((s) => s.setSummaryPanelOpen);

    const openExclusively = (name: InfoPanelName) => {
        setCitationPanelOpen(name === 'citation');
        setChatPanelOpen(name === 'chat');
        setSummaryPanelOpen(name === 'summary');
    };

    const toggle = (name: InfoPanelName) => {
        const isOpen =
            (name === 'citation' && isCitationPanelOpen) ||
            (name === 'chat' && isChatPanelOpen) ||
            (name === 'summary' && isSummaryPanelOpen);
        if (isOpen) {
            if (name === 'citation') setCitationPanelOpen(false);
            else if (name === 'chat') setChatPanelOpen(false);
            else setSummaryPanelOpen(false);
        } else {
            openExclusively(name);
        }
    };

    return {
        isCitationPanelOpen,
        isChatPanelOpen,
        isSummaryPanelOpen,
        toggleCitation: () => toggle('citation'),
        toggleChat: () => toggle('chat'),
        toggleSummary: () => toggle('summary'),
        openCitation: () => openExclusively('citation'),
        openChat: () => openExclusively('chat'),
        openSummary: () => openExclusively('summary'),
    };
}
