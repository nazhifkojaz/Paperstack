import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from './client';

export type InsightKind = 'synthesis' | 'gaps';

export interface PaperChip {
    pdf_id: string;
    title: string;
}
export interface InsightTheme {
    name: string;
    description: string;
    papers: PaperChip[];
}
export interface InsightCardItem {
    title: string;
    description: string;
    papers: PaperChip[];
}

export interface CollectionInsight {
    collection_id: string;
    kind: InsightKind;
    status: 'generating' | 'complete' | 'failed';
    progress_pct: number;
    is_stale: boolean;
    payload: {
        synthesis?: string;
        themes?: InsightTheme[];
        contradictions?: InsightCardItem[];
        gaps?: InsightCardItem[];
        lineages?: InsightCardItem[];
        paper_count?: number;
        skipped_no_summary?: number;
    } | null;
    error_message: string | null;
    model: string | null;
    generated_at: string | null;
}

export interface DuplicatePair {
    pdf_a: { id: string; title: string };
    pdf_b: { id: string; title: string };
    similarity: number;
}

// 404 = no insight row yet -> resolve to null instead of erroring.
const fetchInsightOrNull = async (
    collectionId: string,
    kind: InsightKind,
): Promise<CollectionInsight | null> => {
    try {
        return await apiFetch<CollectionInsight>(
            `/collections/${collectionId}/insights/${kind}`,
        );
    } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
    }
};

export const useCollectionInsight = (
    collectionId: string | null,
    kind: InsightKind,
) => {
    return useQuery({
        queryKey: ['collection-insight', collectionId, kind],
        queryFn: () => fetchInsightOrNull(collectionId!, kind),
        enabled: !!collectionId,
        refetchInterval: (query) => {
            const data = query.state.data as CollectionInsight | null;
            return data?.status === 'generating' ? 2500 : false;
        },
    });
};

export const useGenerateInsight = (kind: InsightKind) => {
    const queryClient = useQueryClient();
    return useMutation<CollectionInsight, Error, string>({
        mutationFn: (collectionId: string) => {
            const path =
                kind === 'synthesis'
                    ? `/collections/${collectionId}/synthesize`
                    : `/collections/${collectionId}/insights/gaps`;
            return apiFetch<CollectionInsight>(path, { method: 'POST' });
        },
        onSuccess: (data, collectionId) => {
            queryClient.setQueryData(
                ['collection-insight', collectionId, kind],
                data,
            );
        },
    });
};

export const useCollectionDuplicates = (collectionId: string | null) => {
    return useQuery({
        queryKey: ['collection-duplicates', collectionId],
        queryFn: (): Promise<{ pairs: DuplicatePair[] }> =>
            apiFetch(`/collections/${collectionId}/duplicates`),
        enabled: !!collectionId,
        staleTime: 5 * 60_000,
    });
};
