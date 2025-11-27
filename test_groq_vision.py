import os
import base64
from dotenv import load_dotenv
from groq import Groq

# Load env vars
load_dotenv(dotenv_path="backend/.env")

api_key = os.getenv('GROQ_API_KEY')
if not api_key:
    print("FAIL: GROQ_API_KEY not found.")
    exit(1)

client = Groq(api_key=api_key)

# Create a simple 1x1 white pixel base64 image
# This is a valid 1x1 PNG
base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNiaaaAAgdboOEAAAAASUVORK5CYII="

print("Testing Groq Vision model: llama-3.2-11b-vision-preview")

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        model="llama-3.2-90b-vision-preview",
    )
    print("SUCCESS!")
    print(chat_completion.choices[0].message.content)
except Exception as e:
    print(f"FAILED: {e}")
