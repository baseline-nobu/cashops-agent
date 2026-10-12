from pathlib import Path
import os
from google import genai

def load_env(path=".env.local"):
    if not Path(path).exists():
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key] = value

load_env()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=(
        "You are the AI reasoning layer of CashOps Agent. "
        "Reply with exactly: CashOps AI ready."
    ),
)

print(response.text)
