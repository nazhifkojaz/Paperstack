import { useEffect, useRef, useState } from 'react';

interface FpsStats {
    fps: number;
    avgFps: number;
    longestFrame: number;
}

export function FpsCounter() {
    const [stats, setStats] = useState<FpsStats>({ fps: 0, avgFps: 0, longestFrame: 0 });
    const frameTimesRef = useRef<number[]>([]);
    const lastFrameRef = useRef<number>(0);
    const lastDisplayUpdateRef = useRef<number>(0);
    const sessionLongestRef = useRef<number>(0);
    const rafRef = useRef<number>(0);

    useEffect(() => {
        const tick = (now: number) => {
            const delta = now - lastFrameRef.current;
            lastFrameRef.current = now;

            frameTimesRef.current.push(delta);
            if (frameTimesRef.current.length > 600) frameTimesRef.current.shift();

            if (delta > sessionLongestRef.current) sessionLongestRef.current = delta;

            if (now - lastDisplayUpdateRef.current >= 250) {
                const recent = frameTimesRef.current.slice(-60);
                const avgDelta = recent.reduce((a, b) => a + b, 0) / recent.length;
                const windowDelta = frameTimesRef.current.reduce((a, b) => a + b, 0) /
                    frameTimesRef.current.length;
                setStats({
                    fps: Math.round(1000 / avgDelta),
                    avgFps: Math.round(1000 / windowDelta),
                    longestFrame: Math.round(sessionLongestRef.current),
                });
                lastDisplayUpdateRef.current = now;
            }

            rafRef.current = requestAnimationFrame(tick);
        };

        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, []);

    const reset = () => {
        frameTimesRef.current = [];
        sessionLongestRef.current = 0;
        lastFrameRef.current = performance.now();
    };

    const color =
        stats.fps >= 50 ? 'text-green-400'
        : stats.fps >= 30 ? 'text-yellow-400'
        : 'text-red-400';

    return (
        <div
            className="fixed bottom-3 right-3 z-[9999] bg-black/80 text-white text-xs font-mono px-3 py-2 rounded shadow-lg pointer-events-auto select-none"
            style={{ minWidth: '150px' }}
        >
            <div className="flex items-baseline gap-2">
                <span className={`text-base font-bold ${color}`}>{stats.fps}</span>
                <span className="text-white/60">fps now</span>
            </div>
            <div className="text-white/70">avg (10s): {stats.avgFps} fps</div>
            <div className="text-white/70">worst frame: {stats.longestFrame} ms</div>
            <button
                onClick={reset}
                className="mt-1 text-[10px] text-white/60 hover:text-white underline"
            >
                reset
            </button>
        </div>
    );
}
