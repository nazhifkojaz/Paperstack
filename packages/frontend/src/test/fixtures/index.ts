/**
 * Mock data fixtures for tests.
 */

export const mockPdf = {
  id: 'pdf-1',
  title: 'Test PDF',
  filename: 'test.pdf',
  file_size: 12345,
  page_count: 10,
  uploaded_at: '2026-03-09T00:00:00Z',
  doi: null,
  isbn: null,
}

export const mockAnnotation = {
  id: 'ann-1',
  set_id: 'set-1',
  page_number: 1,
  type: 'highlight',
  rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }],
  selected_text: null,
  note_content: null,
  color: '#FFFF00',
  created_at: '2026-03-09T00:00:00Z',
}

export const mockAnnotationSet = {
  id: 'set-1',
  pdf_id: 'pdf-1',
  name: 'Default',
  color: '#FFFF00',
  created_at: '2026-03-09T00:00:00Z',
  annotations: [],
}

export const mockCitation = {
  id: 'cit-1',
  pdf_id: 'pdf-1',
  bibtex: '@article{test2024, title={Test Paper}}',
  doi: '10.1234/test',
  title: 'Test Paper',
  authors: 'Test Author',
  year: 2024,
  source: 'manual',
}

export const mockUser = {
  id: 'user-1',
  email: 'test@example.com',
  display_name: 'Test User',
  avatar_url: 'https://example.com/avatar.png',
  storage_provider: 'github' as const,
}

export const mockCollection = {
  id: 'col-1',
  name: 'Research',
  parent_id: null,
  position: 0,
  pdf_count: 0,
}

export const mockTag = {
  id: 'tag-1',
  name: 'Important',
  color: '#FF0000',
  pdf_count: 0,
}
