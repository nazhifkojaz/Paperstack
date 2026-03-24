import { usePdfContent, type Pdf } from '@/api/pdfs';

export function usePdfSource(pdfMetadata: Pdf | undefined) {
    const isLinked = !!pdfMetadata?.source_url && !pdfMetadata?.github_sha;

    // Only fetch content from backend for stored PDFs
    const contentQuery = usePdfContent(
        !isLinked && pdfMetadata ? pdfMetadata.id : ''
    );

    return {
        /** Direct URL for linked PDFs, null for stored PDFs */
        sourceUrl: isLinked ? pdfMetadata!.source_url! : null,
        /** Blob content for stored PDFs, null for linked PDFs */
        blob: !isLinked ? contentQuery.data ?? null : null,
        isLoading: !isLinked && contentQuery.isLoading,
        error: !isLinked ? contentQuery.error : null,
        isLinked,
    };
}
