from pathlib import Path
from dotenv import load_dotenv
import os

# --- Enhanced Debugging for .env Loading ---
print("--- [Config] Attempting to load .env file ---")
env_path = Path(__file__).resolve().parent.parent / ".env"
print(f"[Config] Absolute path to .env: {env_path}")

if env_path.exists():
    print("[Config] .env file found. Loading variables.")
    load_dotenv(dotenv_path=env_path, override=True, verbose=True)
    print("[Config] load_dotenv call complete.")
else:
    print("[Config] .env file NOT found at the specified path.")

print(f"[Config] Value of MAILGUN_SMTP_LOGIN from env: {os.getenv('MAILGUN_SMTP_LOGIN')}")
print("--- [Config] Finished .env load attempt ---")
