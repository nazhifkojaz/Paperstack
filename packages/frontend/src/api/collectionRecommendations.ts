import { useQuery } from '@tanstack/react-query';
import { apiFetch } from './client';

export interface RecommendedPaper {
    openalex_id: string;
    title: string | null;
    authors: string[];
    year: number | null;
    doi: string | null;
    cited_by_count: number;
}

export interface RecommendationsResponse {
    suggestions: RecommendedPaper[];
    papers_total: number;
    papers_with_refs: number;
    papers_without_doi: number;
}

export const useCollectionRecommendations = (
    collectionId: string | null,
    enabled: boolean,
) => {
    return useQuery({
        queryKey: ['collection-recommendations', collectionId],
        queryFn: (): Promise<RecommendationsResponse> =>
            apiFetch(`/collections/${collectionId}/recommendations`),
        enabled: !!collectionId && enabled,
        staleTime: 30 * 60_000, // refs are cached server-side; refetch is cheap but pointless
        retry: 1,
    });
};
