import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path="backend/.env")

client = Groq(api_key=os.getenv('GROQ_API_KEY'))

try:
    models = client.models.list()
    print("Available Groq Models:")
    for m in models.data:
        print(f"- {m.id}")
except Exception as e:
    print(f"Error listing models: {e}")