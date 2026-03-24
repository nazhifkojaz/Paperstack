import { Outlet } from 'react-router-dom';
import { TopBar } from '@/components/TopBar';
import { Sidebar } from '@/components/Sidebar';
import { useUIStore } from '@/stores/uiStore';

export function AppLayout() {
    const { sidebarOpen, closeSidebar } = useUIStore();

    return (
        <div className="flex flex-col h-screen overflow-hidden">
            <TopBar />
            <div className="flex flex-1 min-h-0">
                {/* Desktop sidebar */}
                <Sidebar className="hidden md:flex flex-col w-64 border-r shrink-0 h-full overflow-hidden bg-background" />

                {/* Mobile sidebar overlay */}
                {sidebarOpen && (
                    <>
                        <div
                            className="fixed inset-0 z-40 bg-black/50 md:hidden"
                            onClick={closeSidebar}
                        />
                        <Sidebar className="fixed inset-y-0 left-0 z-50 flex flex-col w-64 border-r bg-background md:hidden" />
                    </>
                )}

                <main className="flex-1 min-h-0 overflow-auto bg-background">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
