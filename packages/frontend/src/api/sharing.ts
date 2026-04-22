import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

export interface Share {
    id: string;
    annotation_set_id: string;
    shared_by: string;
    shared_with: string | null;
    shared_with_github_login?: string | null;
    share_token: string;
    permission: 'view' | 'comment';
    created_at: string;
}

interface ShareCreate {
    shared_with_github_login?: string;
    permission?: 'view' | 'comment';
}

interface AnnotationData {
    id: string;
    set_id: string;
    page_number: number;
    type: string;
    rects: Array<{ x: number; y: number; w: number; h: number }>;
    selected_text?: string | null;
    note_content?: string | null;
    color?: string | null;
}

interface SharedAnnotationsResponse {
    shared_by_login: string;
    shared_by_avatar: string | null;
    permission: string;
    annotation_set: {
        id: string;
        pdf_id: string;
        name: string;
        color: string;
        annotations: AnnotationData[];
    };
    pdf_id: string;
    pdf_title: string;
}

// Queries

export const useSharesForSet = (setId: string) =>
    useQuery<Share[]>({
        queryKey: ['shares', setId],
        queryFn: () => apiFetch(`/annotation-sets/${setId}/shares`),
        enabled: !!setId,
    });

/** Public — no auth required. Used on /shared/:token page. */
export const useSharedAnnotations = (token: string) =>
    useQuery<SharedAnnotationsResponse>({
        queryKey: ['shared-annotations', token],
        queryFn: () => apiFetch(`/shared/annotations/${token}`, { authRequired: false }),
        enabled: !!token,
        retry: false,
    });

// Mutations

export const useCreateShare = (setId: string) => {
    const qc = useQueryClient();
    return useMutation<Share, Error, ShareCreate>({
        mutationFn: (data) =>
            apiFetch(`/annotation-sets/${setId}/share`, {
                method: 'POST',
                body: JSON.stringify(data),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['shares', setId] }),
    });
};

export const useRevokeShare = () => {
    const qc = useQueryClient();
    return useMutation<void, Error, string>({
        mutationFn: (shareId) => apiFetch(`/shares/${shareId}`, { method: 'DELETE' }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['shares'] }),
    });
};
