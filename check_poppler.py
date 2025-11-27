
import sys
try:
    from pdf2image import convert_from_bytes
    print("pdf2image imported successfully")
except ImportError:
    print("pdf2image not installed")
    sys.exit(1)

try:
    # Minimal PDF
    pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000117 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n223\n%%EOF"
    
    print("Attempting to convert PDF to image...")
    images = convert_from_bytes(pdf_bytes)
    print(f"Success! Converted {len(images)} pages.")
except Exception as e:
    print(f"Conversion failed: {e}")
