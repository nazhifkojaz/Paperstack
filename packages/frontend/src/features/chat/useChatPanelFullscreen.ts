import { useEffect } from 'react';

export function useChatPanelFullscreen(
  isOpen: boolean,
  isFullscreen: boolean,
  setFullscreen: (fullscreen: boolean) => void,
) {
  useEffect(() => {
    if (!isFullscreen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isFullscreen, setFullscreen]);

  useEffect(() => {
    if (!isOpen) setFullscreen(false);
  }, [isOpen, setFullscreen]);
}
