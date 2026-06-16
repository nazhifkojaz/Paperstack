import { useOnboardingStore } from '@/stores/onboardingStore';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Key, Database, Sparkles, AlertCircle } from 'lucide-react';

interface SettingsOnboardingModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsOnboardingModal({ open, onOpenChange }: SettingsOnboardingModalProps) {
  const { markSettingsOnboardingSeen } = useOnboardingStore();

  const handleClose = () => {
    markSettingsOnboardingSeen();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Welcome to Paperstack</DialogTitle>
          <DialogDescription>
            A quick guide to the settings that power your research workflow.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Storage Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-medium">Storage</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              Paperstack stores your PDFs in your own cloud account. Choose between:
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border p-3 space-y-1">
                <p className="text-sm font-medium">Google Drive</p>
                <p className="text-xs text-muted-foreground">PDFs stored in a Paperstack folder in your Drive.</p>
              </div>
              <div className="rounded-lg border p-3 space-y-1">
                <p className="text-sm font-medium">GitHub</p>
                <p className="text-xs text-muted-foreground">PDFs stored in a private paperstack-library repository.</p>
              </div>
            </div>
          </div>

          <Separator />

          {/* AI Models Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-500" />
              <h3 className="text-sm font-medium">AI Models</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              Paperstack uses AI for chat, auto-highlight, and explanations. You can use:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <span className="text-primary font-medium shrink-0">App Key</span>
                <span>Free tier with daily limits. Good for getting started.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-primary font-medium shrink-0">BYOK</span>
                <span>Bring Your Own OpenRouter key for unlimited usage and access to premium models.</span>
              </li>
            </ul>
          </div>

          <Separator />

          {/* Quotas Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              <h3 className="text-sm font-medium">Daily Quotas</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              The free tier has daily limits for AI features (chat, explain, auto-highlight). Check your remaining quota in the auto-highlight panel. Add your own OpenRouter key to remove these limits.
            </p>
          </div>

          <Separator />

          {/* OpenRouter Key */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Key className="h-4 w-4 text-blue-500" />
              <h3 className="text-sm font-medium">OpenRouter API Key</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              If you choose BYOK mode, add your OpenRouter key in Settings. You can get one for free at{' '}
              <a
                href="https://openrouter.ai/settings/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:underline"
              >
                openrouter.ai
              </a>
              . Embeddings will try your key first, then fall back to the app key if needed.
            </p>
          </div>
        </div>

        <div className="flex justify-end mt-6">
          <Button onClick={handleClose}>Got it, let's go</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
