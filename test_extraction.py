import os
import sys
import base64 as import_base64
from dotenv import load_dotenv
from groq import Groq

# Load env
load_dotenv()
load_dotenv(dotenv_path="backend/.env")

# Setup Groq
api_key = os.getenv('GROQ_API_KEY')
groq_client = Groq(api_key=api_key) if api_key else None
print(f"Groq Client: {bool(groq_client)}")

if groq_client:
    print("Listing available models...")
    try:
        models = groq_client.models.list()
        for m in models.data:
            print(f" - {m.id}")
    except Exception as e:
        print(f"Failed to list models: {e}")

# Import helper
sys.path.append('backend')
from ocr_helper import extract_text_from_pdf_stream

# Create dummy PDF with minimal text
from reportlab.pdfgen import canvas
import io

buffer = io.BytesIO()
c = canvas.Canvas(buffer)
c.drawString(100, 750, "Short text")
c.save()
pdf_bytes = buffer.getvalue()

print(f"Created PDF with {len(pdf_bytes)} bytes")

# Run extraction
print("Running extraction...")
try:
    # Try to force the model in the helper for testing, or we can just test the call directly here
    # But better to test via helper if we can inject it, but helper hardcodes it.
    # So let's just test the API call directly here to find a working model.
    
    img_byte_arr = io.BytesIO()
    # Create a dummy image
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (100, 30), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10,10), "Hello World", fill=(255, 255, 0))
    img.save(img_byte_arr, format='JPEG')
    img_base64 = import_base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    models_to_try = [
        "llama-3.2-11b-vision-preview", # Known bad
        "llama-3.2-11b-vision-instruct", 
        "llama-3.2-90b-vision-instruct",
        "llama-3.2-11b-vision",
        "llama-3.2-90b-vision"
    ]
    
    for model in models_to_try:
        print(f"Testing model: {model}")
        try:
            completion = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Read this."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                        ]
                    }
                ],
                max_tokens=10
            )
            print(f"SUCCESS with {model}: {completion.choices[0].message.content}")
            break
        except Exception as e:
            print(f"FAILED {model}: {e}")

except Exception as e:
    print(f"CRASH: {e}")
    import traceback
    traceback.print_exc()
