import { useState } from 'react';
import { Library, Menu, Settings } from 'lucide-react';
import { UserNav } from './UserNav';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useUIStore } from '@/stores/uiStore';
import { SettingsDialog } from '@/features/settings/SettingsDialog';

export const TopBar = () => {
    const { toggleSidebar } = useUIStore();
    const [settingsOpen, setSettingsOpen] = useState(false);

    return (
        <>
            <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between border-b bg-background px-4 md:px-6">
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="md:hidden h-9 w-9"
                        onClick={toggleSidebar}
                    >
                        <Menu className="h-5 w-5" />
                        <span className="sr-only">Toggle sidebar</span>
                    </Button>
                    <Link to="/" className="flex items-center gap-2 font-semibold">
                        <Library className="h-5 w-5 text-primary" />
                        <span>Paperstack</span>
                    </Link>
                </div>

                <div className="flex items-center gap-2 ml-auto">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        onClick={() => setSettingsOpen(true)}
                    >
                        <Settings className="h-5 w-5" />
                        <span className="sr-only">Settings</span>
                    </Button>
                    <UserNav />
                </div>
            </header>

            <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
        </>
    );
};
