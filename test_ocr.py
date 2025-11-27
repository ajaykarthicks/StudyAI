
import os
import sys
import io
from dotenv import load_dotenv

# Load env vars
load_dotenv()
load_dotenv(dotenv_path="backend/.env")

print("--- Testing Environment ---")

# 1. Test Fitz (PyMuPDF)
print("\n1. Testing PyMuPDF (fitz)...")
try:
    import fitz
    print(f"Fitz version: {fitz.__doc__}")
    
    # Create a dummy PDF in memory
    pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000117 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n223\n%%EOF"
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    print(f"Successfully opened PDF with {len(doc)} pages.")
    
    # Try to render
    pix = doc[0].get_pixmap()
    print(f"Successfully rendered page to image: {pix.width}x{pix.height}")
    
except ImportError:
    print("FAIL: fitz not installed.")
except Exception as e:
    print(f"FAIL: fitz error: {e}")

# 2. Test Groq
print("\n2. Testing Groq Client...")
try:
    from groq import Groq
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        print("FAIL: GROQ_API_KEY not found in environment.")
    else:
        print(f"GROQ_API_KEY found (starts with {api_key[:4]}...)")
        client = Groq(api_key=api_key)
        
        # Simple chat completion
        print("Sending test request to Groq...")
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "Say 'Hello World'",
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        print(f"Groq Response: {chat_completion.choices[0].message.content}")
        
except ImportError:
    print("FAIL: groq library not installed.")
except Exception as e:
    print(f"FAIL: Groq error: {e}")

# 3. Test EasyOCR
print("\n3. Testing EasyOCR...")
try:
    import easyocr
    import numpy as np
    print("EasyOCR imported successfully.")
    
    # Initialize reader
    print("Initializing reader (this may take a moment)...")
    reader = easyocr.Reader(['en'], gpu=False)
    print("Reader initialized.")
    
    # Create a dummy image (black square)
    dummy_image = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # Run OCR (should return nothing, but verify it runs)
    result = reader.readtext(dummy_image)
    print("EasyOCR run successfully (result empty as expected for black image).")
    
except ImportError:
    print("FAIL: easyocr not installed.")
except Exception as e:
    print(f"FAIL: EasyOCR error: {e}")

print("\n--- End Test ---")
