import { useOnboardingStore } from '@/stores/onboardingStore';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { HelpCircle, BookOpen, Copy, Check } from 'lucide-react';
import { useState } from 'react';

const SAMPLE_BIBTEX = `@article{sample2024,
  title={Sample Paper Title},
  author={Author, A.},
  journal={Journal Name},
  year={2024}
}`;

export function CitationHelp() {
  const { hasSeenCitationHelp, markCitationHelpSeen } = useOnboardingStore();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen && !hasSeenCitationHelp) {
      markCitationHelpSeen();
    }
  };

  const handleCopySample = () => {
    navigator.clipboard.writeText(SAMPLE_BIBTEX);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          title="Citation help"
        >
          <HelpCircle className="h-4 w-4 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-4 space-y-3" align="end">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm">Citation Help</h3>
        </div>
        <p className="text-sm text-muted-foreground">
          Paperstack extracts citations from your PDFs automatically. You can:
        </p>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li className="flex items-start gap-2">
            <span className="text-primary font-medium shrink-0">Auto-extract</span>
            <span>Click "Auto-extract" to pull metadata from the PDF.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-primary font-medium shrink-0">Edit</span>
            <span>Click the pencil icon to manually correct any field.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-primary font-medium shrink-0">Export</span>
            <span>Copy the BibTeX block to use in LaTeX, Zotero, or other reference managers.</span>
          </li>
        </ul>
        <div className="rounded-lg bg-muted p-2 space-y-1">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-muted-foreground">BibTeX format</p>
            <Button variant="ghost" size="sm" className="h-6 gap-1 text-xs" onClick={handleCopySample}>
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? 'Copied!' : 'Copy sample'}
            </Button>
          </div>
          <pre className="text-xs font-mono text-muted-foreground overflow-auto whitespace-pre-wrap">
            {SAMPLE_BIBTEX}
          </pre>
        </div>
      </PopoverContent>
    </Popover>
  );
}
