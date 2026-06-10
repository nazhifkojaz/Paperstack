import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';
import { DEFAULT_COLOR_LABELS } from '@/features/annotations/constants';

export interface ColorLabelsResponse {
    labels: Record<string, string>;
}

export interface ColorLabelsUpdate {
    labels: Record<string, string>;
}

export const useColorLabels = () => {
    return useQuery({
        queryKey: ['color-labels'],
        queryFn: (): Promise<ColorLabelsResponse> => apiFetch('/settings/color-labels'),
        select: (data): Record<string, string> => {
            const merged = { ...DEFAULT_COLOR_LABELS };
            if (data.labels) {
                Object.assign(merged, data.labels);
            }
            return merged;
        },
    });
};

export const useUpdateColorLabels = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: ColorLabelsUpdate): Promise<ColorLabelsResponse> =>
            apiFetch('/settings/color-labels', {
                method: 'PATCH',
                body: JSON.stringify(data),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['color-labels'] });
        },
    });
};
