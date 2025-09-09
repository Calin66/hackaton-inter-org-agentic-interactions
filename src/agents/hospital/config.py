from dotenv import load_dotenv

def init_env() -> None:
    # Load .env if present; don't override OS-provided env vars
    load_dotenv(override=False)
