/**
 * Browser download utilities.
 * Handles triggering file downloads from Blobs in a safe, cleanup-friendly way.
 */

/**
 * Triggers a browser download for a Blob with automatic cleanup.
 * Creates a temporary object URL, triggers download via a temporary anchor element,
 * and cleans up both the element and the object URL.
 *
 * @param blob - The file content as a Blob
 * @param filename - The filename to save as (e.g., "document.pdf")
 *
 * @example
 * const pdfBlob = await apiFetchBlob('/pdfs/1/export');
 * downloadBlob(pdfBlob, 'research-paper.pdf');
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;

  // Append to DOM, click, then cleanup
  document.body.appendChild(anchor);
  anchor.click();

  // Cleanup
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}
