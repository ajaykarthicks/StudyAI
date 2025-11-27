import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path="backend/.env")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

try:
    print("Testing llama-3.2-11b-vision-preview...")
    completion = client.chat.completions.create(
        model="llama-3.2-11b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": "What is in this image?",
            }
        ],
        temperature=1,
        max_tokens=1024,
        top_p=1,
        stream=False,
        stop=None,
    )
    print("Success!")
    print(completion.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
