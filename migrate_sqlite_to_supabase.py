import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker

# Add backend to path to import models if needed, though we might just use reflection
sys.path.append(str(Path(__file__).parent / "backend"))

# Load env to get Supabase URL
env_path = Path(__file__).parent / "backend" / ".env"
load_dotenv(env_path)

SUPABASE_URL = os.getenv("DATABASE_URL")
SQLITE_PATH = Path(__file__).parent / "backend" / "instance" / "studyai.db"
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

def migrate():
    print("--- Migration: SQLite -> Supabase ---")
    
    if not SQLITE_PATH.exists():
        print(f"Error: SQLite database not found at {SQLITE_PATH}")
        return

    if not SUPABASE_URL:
        print("Error: DATABASE_URL not found in .env")
        return

    # Fix URL for pg8000 if needed (same logic as db.py)
    final_supabase_url = SUPABASE_URL
    if final_supabase_url.startswith("postgres://"):
        final_supabase_url = final_supabase_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif final_supabase_url.startswith("postgresql://"):
        final_supabase_url = final_supabase_url.replace("postgresql://", "postgresql+pg8000://", 1)

    print(f"SQLite: {SQLITE_URL}")
    print(f"Supabase: {final_supabase_url.split('@')[-1]}")

    # Create Engines
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(final_supabase_url)

    # Tables in dependency order
    tables_to_migrate = [
        "users",
        "pdf_uploads",
        "login_events",
        "daily_upload_stats",
        "photo_capture_events",
        "feature_usages",
        "notes"
    ]

    # Reflect tables
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)
    
    pg_meta = MetaData()
    pg_meta.reflect(bind=pg_engine)

    with pg_engine.connect() as pg_conn:
        # Clear existing data in reverse order to handle foreign keys
        print("\nCleaning destination tables...")
        tables_to_clean = reversed(tables_to_migrate)
        for table_name in tables_to_clean:
            if table_name in pg_meta.tables:
                try:
                    print(f"  - Truncating {table_name}...")
                    pg_conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
                    pg_conn.commit()
                except Exception as e:
                    print(f"    ! Error truncating {table_name}: {e}")
                    pg_conn.rollback()
        
        for table_name in tables_to_migrate:
            print(f"\nMigrating table: {table_name}...")
            
            if table_name not in sqlite_meta.tables:
                print(f"  - Table {table_name} not found in SQLite. Skipping.")
                continue
                
            if table_name not in pg_meta.tables:
                print(f"  - Table {table_name} not found in Supabase. Creating it first...")
                # We should probably run init_db() logic, but let's assume the user ran the app once against Supabase
                # or we can try to create it using the model definition.
                # For now, let's warn.
                print(f"  ! WARNING: Table {table_name} does not exist in destination. Please run the app once against Supabase to create tables.")
                continue

            sqlite_table = sqlite_meta.tables[table_name]
            pg_table = pg_meta.tables[table_name]

            # Read from SQLite
            with sqlite_engine.connect() as sqlite_conn:
                rows = sqlite_conn.execute(sqlite_table.select()).fetchall()
                
            if not rows:
                print("  - No data to migrate.")
                continue
                
            print(f"  - Found {len(rows)} rows.")
            
            # Insert into Postgres
            # We convert rows to dicts
            data_to_insert = []
            for row in rows:
                # Convert row to dict safely
                row_dict = dict(row._mapping)
                
                # Handle boolean conversion for SQLite (0/1) to Postgres (True/False)
                # SQLAlchemy usually handles this if reflected correctly, but let's be safe
                if table_name == "users":
                    if 'photo_capture_enabled' in row_dict:
                        row_dict['photo_capture_enabled'] = bool(row_dict['photo_capture_enabled'])
                
                data_to_insert.append(row_dict)

            # Batch insert
            try:
                # Use postgres insert with ON CONFLICT DO NOTHING to avoid duplicates if run multiple times
                # But standard insert is safer to detect issues.
                # We'll just try to insert. If it fails, we might need to truncate or handle conflicts.
                # For a clean migration, we assume destination is empty or we want to append.
                # Let's try simple insert.
                
                pg_conn.execute(pg_table.insert(), data_to_insert)
                pg_conn.commit()
                print(f"  - Successfully inserted {len(data_to_insert)} rows.")
                
                # Update sequence
                # Postgres sequences need to be reset to max(id)
                if 'id' in pg_table.columns:
                    print("  - Updating sequence...")
                    max_id = pg_conn.execute(text(f"SELECT MAX(id) FROM {table_name}")).scalar() or 0
                    # Sequence name is usually table_id_seq
                    seq_name = f"{table_name}_id_seq"
                    try:
                        pg_conn.execute(text(f"SELECT setval('{seq_name}', {max_id + 1}, false)"))
                        pg_conn.commit()
                    except Exception as e:
                        print(f"    ! Could not update sequence (might not exist or different name): {e}")
                        pg_conn.rollback()

            except Exception as e:
                print(f"  ! Error inserting data: {e}")
                pg_conn.rollback()

    print("\nMigration completed.")

if __name__ == "__main__":
    migrate()
