import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv('backend/.env')

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("No API key found in backend/.env")
    exit(1)

genai.configure(api_key=api_key)

print("Listing available models...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"Model: {m.name}")
            print(f"  Display Name: {m.display_name}")
            print(f"  Supported Methods: {m.supported_generation_methods}")
            print("-" * 20)
except Exception as e:
    print(f"Error listing models: {e}")
