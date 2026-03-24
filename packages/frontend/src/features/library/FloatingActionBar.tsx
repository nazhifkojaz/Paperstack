import { Download, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface FloatingActionBarProps {
    selectedCount: number;
    onExport: () => void;
    onCancel: () => void;
}

export const FloatingActionBar = ({ selectedCount, onExport, onCancel }: FloatingActionBarProps) => {
    if (selectedCount === 0) {
        return null;
    }

    return (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-200">
            <div className="bg-gray-900 text-white px-5 py-3 rounded-full shadow-lg flex items-center gap-3">
                <span className="font-medium text-sm">
                    {selectedCount} selected
                </span>
                <div className="w-px h-5 bg-gray-600" />
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={onCancel}
                    className="text-gray-300 hover:text-white hover:bg-gray-800 h-8 px-3"
                >
                    <X className="h-4 w-4 mr-1" />
                    Cancel
                </Button>
                <Button
                    size="sm"
                    onClick={onExport}
                    className="bg-blue-600 hover:bg-blue-700 text-white h-8 px-3"
                >
                    <Download className="h-4 w-4 mr-1" />
                    Export BibTeX
                </Button>
            </div>
        </div>
    );
};
