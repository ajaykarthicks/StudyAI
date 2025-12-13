import os
import sys
import socket
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

# Load env
env_path = Path(__file__).parent / "backend" / ".env"
if env_path.exists():
    print(f"Loading .env from {env_path}")
    load_dotenv(env_path)
else:
    print("Warning: backend/.env not found")

DATABASE_URL = os.getenv("DATABASE_URL")

def check_connection():
    print("\n--- Database Connection Check ---")
    
    final_url = DATABASE_URL
    
    if not final_url:
        print("DATABASE_URL is not set in backend/.env")
        print("Defaulting to SQLite (local mode).")
        # Construct absolute path to sqlite db to be safe
        db_path = Path(__file__).parent / "backend" / "instance" / "studyai.db"
        final_url = f"sqlite:///{db_path}"
    else:
        print(f"DATABASE_URL found: {final_url.split('@')[-1] if '@' in final_url else '***'}")

    # Check DNS resolution if Postgres
    if final_url and ("postgres" in final_url or "supabase" in final_url):
        try:
            # Parse hostname
            # Handle potential sqlalchemy prefixes for parsing
            temp_url = final_url
            if "postgresql+pg8000://" in temp_url:
                temp_url = temp_url.replace("postgresql+pg8000://", "postgres://")
            
            parsed = urlparse(temp_url)
            hostname = parsed.hostname
            port = parsed.port or 5432
            
            if hostname:
                print(f"\n[DNS] Resolving {hostname}...")
                try:
                    infos = socket.getaddrinfo(hostname, port)
                    seen = set()
                    for family, type, proto, canonname, sockaddr in infos:
                        ip = sockaddr[0]
                        if ip in seen:
                            continue
                        seen.add(ip)
                        fam_str = "IPv4" if family == socket.AF_INET else "IPv6" if family == socket.AF_INET6 else str(family)
                        print(f"  - {fam_str}: {ip}")
                except Exception as e:
                    print(f"  [DNS Error] {e}")
            
        except Exception as e:
            print(f"[DNS] Resolution setup failed: {e}")

    # Prepare URL for SQLAlchemy
    if final_url and "postgres" in final_url:
        if final_url.startswith("postgres://"):
            final_url = final_url.replace("postgres://", "postgresql+pg8000://", 1)
        elif final_url.startswith("postgresql://"):
            final_url = final_url.replace("postgresql://", "postgresql+pg8000://", 1)

    print(f"\n[Connection] Attempting to connect...")
    print(f"Dialect: {final_url.split('://')[0]}")
    
    try:
        engine = create_engine(final_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            val = result.scalar()
            print(f"[Success] Connection successful! Query 'SELECT 1' returned: {val}")
            
    except Exception as e:
        print(f"[Error] Connection failed!")
        print(f"Details: {e}")

if __name__ == "__main__":
    check_connection()
