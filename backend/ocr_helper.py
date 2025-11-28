import io
import logging
import base64
import os
import time
import PyPDF2
from typing import List, Optional

# Try importing PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    logging.warning("PyMuPDF (fitz) not found. Install pymupdf.")

# Try importing EasyOCR (Lazy load)
EASYOCR_AVAILABLE = None # Will be checked on first use

# Try importing OCR libraries (Tesseract & Pillow)
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logging.warning("pytesseract or Pillow not found.")

# Try pdf2image as fallback
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

# Try importing Google Generative AI (Gemini)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-generativeai not found. Install it for Gemini Vision support.")

# Initialize EasyOCR reader (lazy load)
_reader = None
easyocr_module = None
cv2_module = None
np_module = None

def ensure_easyocr():
    global EASYOCR_AVAILABLE, easyocr_module, cv2_module, np_module
    if EASYOCR_AVAILABLE is not None:
        return EASYOCR_AVAILABLE
        
    try:
        import easyocr
        import numpy as np
        import cv2
        easyocr_module = easyocr
        cv2_module = cv2
        np_module = np
        EASYOCR_AVAILABLE = True
        print("[OCR] EasyOCR modules loaded successfully")
    except ImportError as e:
        EASYOCR_AVAILABLE = False
        logging.warning(f"EasyOCR or OpenCV not found: {e}")
        
    return EASYOCR_AVAILABLE

def get_easyocr_reader():
    global _reader
    if not ensure_easyocr():
        return None
        
    if _reader is None:
        print("[OCR] Initializing EasyOCR reader...")
        # 'en' for English. Add more languages if needed.
        # gpu=False to be safe on standard environments, or True if CUDA available
        try:
            _reader = easyocr_module.Reader(['en'], gpu=False) 
        except Exception as e:
            logging.warning(f"Failed to init EasyOCR: {e}")
    return _reader

def preprocess_image_for_ocr(pil_image):
    """
    Preprocess image for better OCR accuracy (especially handwriting).
    1. Grayscale
    2. Denoise
    3. Adaptive Thresholding
    """
    if not ensure_easyocr():
        return np_module.array(pil_image) if np_module else None

    try:
        # Convert PIL to OpenCV format (RGB -> BGR)
        img = np_module.array(pil_image)
        img = cv2_module.cvtColor(img, cv2_module.COLOR_RGB2BGR)

        # Convert to grayscale
        gray = cv2_module.cvtColor(img, cv2_module.COLOR_BGR2GRAY)

        # Denoise (remove salt-and-pepper noise)
        # h=10 is a good starting point for strength
        denoised = cv2_module.fastNlMeansDenoising(gray, h=10)

        # Adaptive Thresholding (Gaussian)
        # Block size 11, C=2
        thresh = cv2_module.adaptiveThreshold(
            denoised, 255, cv2_module.ADAPTIVE_THRESH_GAUSSIAN_C, cv2_module.THRESH_BINARY, 11, 2
        )
        
        return thresh
    except Exception as e:
        print(f"[OCR] Preprocessing failed: {e}")
        return np_module.array(pil_image) # Fallback to original

def extract_text_from_pdf_stream(pdf_bytes: bytes, groq_client=None, progress_callback=None):
    """
    Generator that yields progress updates and finally the extracted text.
    Yields: {"status": "progress"|"complete", "message": str, "percent": int, "text": str|None}
    """
    yield {"status": "progress", "message": "Processing the type of PDF...", "percent": 5}

    print(f"[OCR] Starting extraction. Bytes: {len(pdf_bytes)}")
    
    # Check for Gemini API Key
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if GEMINI_AVAILABLE and gemini_api_key:
        genai.configure(api_key=gemini_api_key)
    
    pdf_stream = io.BytesIO(pdf_bytes)
    try:
        reader = PyPDF2.PdfReader(pdf_stream)
        total_pages = len(reader.pages)
    except Exception as e:
        print(f"[OCR] PyPDF2 failed: {e}")
        yield {"status": "error", "message": f"Failed to read PDF: {e}"}
        return
    
    full_text = []
    
    # Open with fitz if available
    doc = None
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            print(f"[OCR] Failed to open PDF with fitz: {e}")
    
    gemini_request_count = 0

    for i, page in enumerate(reader.pages):
        # Calculate progress: 10% to 90% allocated for pages
        current_progress = 10 + int((i / total_pages) * 80)
        yield {"status": "progress", "message": f"Processing page {i+1} of {total_pages}...", "percent": current_progress}

        text = page.extract_text() or ""
        
        # Heuristic: If text is very short (e.g. < 50 chars)
        if len(text.strip()) < 50:
            yield {"status": "progress", "message": f"Processing page {i+1}: Text seems like handwritten or image. Using Vision AI (takes longer)...", "percent": current_progress}
            
            pil_image = None
            
            # 1. Get Image using Fitz (Preferred)
            if FITZ_AVAILABLE and doc:
                try:
                    # Render page to image
                    # Use matrix to get higher resolution (zoom=2)
                    mat = fitz.Matrix(2, 2)
                    pix = doc[i].get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    if OCR_AVAILABLE or GEMINI_AVAILABLE: # Need PIL Image
                        pil_image = Image.open(io.BytesIO(img_data))
                except Exception as e:
                    print(f"[OCR] Fitz render failed for page {i}: {e}")
            
            # 2. Fallback to pdf2image
            if not pil_image and PDF2IMAGE_AVAILABLE:
                try:
                    images = convert_from_bytes(
                        pdf_bytes, 
                        first_page=i+1, 
                        last_page=i+1,
                        fmt='jpeg'
                    )
                    if images:
                        pil_image = images[0]
                except Exception as e:
                    print(f"[OCR] pdf2image failed for page {i}: {e}")

            # If we have an image, try Vision (Gemini) then OCR
            if pil_image:
                # Try Gemini Vision (Best for handwriting)
                if GEMINI_AVAILABLE and gemini_api_key:
                    try:
                        # Rate Limiting: 30 requests per minute.
                        # If we hit 25 requests, wait for 70 seconds.
                        if gemini_request_count > 0 and gemini_request_count % 25 == 0:
                            wait_time = 70
                            print(f"[OCR] Rate limit check: Hit {gemini_request_count} requests. Waiting {wait_time}s...")
                            yield {"status": "progress", "message": f"Rate limit reached. Waiting {wait_time}s before continuing...", "percent": current_progress}
                            time.sleep(wait_time)
                        
                        print(f"[OCR] Attempting Gemini Vision for page {i+1}...")
                        # Use gemini-2.0-flash-lite as requested
                        model = genai.GenerativeModel('gemini-2.0-flash-lite')
                        response = model.generate_content([
                            "Transcribe the text in this image exactly. Return only the text.",
                            pil_image
                        ])
                        gemini_request_count += 1
                        
                        vision_text = response.text
                        if len(vision_text.strip()) > len(text.strip()):
                            text = vision_text
                            yield {"status": "progress", "message": f"Processing page {i+1}: Extracted text with Gemini Vision", "percent": current_progress}
                            full_text.append(text)
                            continue 
                    except Exception as ve:
                        print(f"[OCR] Gemini Vision failed: {ve}")

                # Try Tesseract (Lighter than EasyOCR)
                if OCR_AVAILABLE and len(text.strip()) < 50:
                    try:
                        ocr_text = pytesseract.image_to_string(pil_image)
                        if len(ocr_text.strip()) > 50: # If Tesseract found good text, use it
                            text = ocr_text
                            yield {"status": "progress", "message": f"Processing page {i+1}: Extracted text with Tesseract", "percent": current_progress}
                            full_text.append(text)
                            continue # Skip EasyOCR if Tesseract worked well
                    except Exception as e:
                        print(f"[OCR] Tesseract failed: {e}")

                # Try EasyOCR (Heavy, use as last resort)
                if ensure_easyocr():
                    try:
                        reader_inst = get_easyocr_reader()
                        if reader_inst:
                            # Preprocess image
                            processed_img = preprocess_image_for_ocr(pil_image)
                            
                            # Run OCR on processed image
                            result = reader_inst.readtext(processed_img, detail=0)
                            easy_text = " ".join(result)
                            
                            # If result is still poor, try raw image
                            if len(easy_text.strip()) < 10:
                                raw_img = np_module.array(pil_image)
                                result_raw = reader_inst.readtext(raw_img, detail=0)
                                easy_text_raw = " ".join(result_raw)
                                if len(easy_text_raw) > len(easy_text):
                                    easy_text = easy_text_raw
                            
                            if len(easy_text.strip()) > len(text.strip()):
                                text = easy_text
                    except Exception as e:
                        print(f"[OCR] EasyOCR failed: {e}")
            else:
                print(f"[OCR] No image generated for page {i+1}, skipping OCR/Vision")
        else:
             yield {"status": "progress", "message": f"Processing page {i+1}: Extracted text from page {i+1}", "percent": current_progress}
        
        full_text.append(text)
        
    if doc:
        doc.close()
        
    final_text = "\n".join([str(t) for t in full_text])
    yield {"status": "complete", "text": final_text, "percent": 100}
