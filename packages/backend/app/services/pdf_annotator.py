import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

from app.schemas.types import AnnotationExportDict

def export_annotated_pdf(original_pdf_bytes: bytes, annotations: list[AnnotationExportDict]) -> bytes:
    """
    Bake annotations into a PDF.
    
    Args:
        original_pdf_bytes: Raw bytes of the original PDF
        annotations: A list of annotation dictionaries, typically joined from Annotation models.
                     Expected keys: page_number (1-indexed), type, color, rects
                     
    Returns:
        Bytes of the new annotated PDF
    """
    if not annotations:
        return original_pdf_bytes
        
    reader = PdfReader(io.BytesIO(original_pdf_bytes))
    writer = PdfWriter()
    
    # Group annotations by page
    page_annotations = {}
    for ann in annotations:
        page_num = ann.get('page_number')
        if page_num not in page_annotations:
            page_annotations[page_num] = []
        page_annotations[page_num].append(ann)
        
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        page_num = i + 1
        
        if page_num in page_annotations:
            # Create a reportlab canvas in an in-memory buffer
            packet = io.BytesIO()
            # Get original page size
            mb = page.mediabox
            width = float(mb.width)
            height = float(mb.height)
            
            c = canvas.Canvas(packet, pagesize=(width, height))
            
            for ann in page_annotations[page_num]:
                if ann.get('type') == 'highlight' or ann.get('type') == 'rect':
                    # Parse colors
                    color_hex = ann.get('color') or '#FFFF00'
                    color = HexColor(color_hex)
                    
                    if ann.get('type') == 'highlight':
                        # Make highlight translucent
                        c.setFillColor(color)
                        c.setFillAlpha(0.3)
                        c.setStrokeAlpha(0.0)
                        
                        rects = ann.get('rects', [])
                        for r in rects:
                            # Frontend coordinates are assumed to be normalized [0, 1] relative to top-left
                            # or exact coordinates... 
                            # If normalized: [x_min, y_min, x_max, y_max] or similar?
                            # Let's assume normalized [x, y, w, h] from 0 to 1, with origin at top left
                            x_norm = r.get('x', 0)
                            y_norm = r.get('y', 0)
                            w_norm = r.get('w', 0)
                            h_norm = r.get('h', 0)
                            
                            x = x_norm * width
                            w = w_norm * width
                            h = h_norm * height
                            # Reportlab origin is bottom left, so:
                            y = height - (y_norm * height) - h
                            
                            c.rect(x, y, w, h, stroke=0, fill=1)
                    
                    elif ann.get('type') == 'rect':
                        # Draw outline
                        c.setStrokeColor(color)
                        c.setLineWidth(2)
                        c.setFillAlpha(0.0)
                        
                        rects = ann.get('rects', [])
                        for r in rects:
                            x_norm = r.get('x', 0)
                            y_norm = r.get('y', 0)
                            w_norm = r.get('w', 0)
                            h_norm = r.get('h', 0)
                            
                            x = x_norm * width
                            w = w_norm * width
                            h = h_norm * height
                            y = height - (y_norm * height) - h
                            
                            c.rect(x, y, w, h, stroke=1, fill=0)

            c.save()
            
            # Merge the newly drawn canvas to the original page
            packet.seek(0)
            overlay_pdf = PdfReader(packet)
            
            if len(overlay_pdf.pages) > 0:
                overlay_page = overlay_pdf.pages[0]
                page.merge_page(overlay_page)
                
        writer.add_page(page)
        
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output.read()
