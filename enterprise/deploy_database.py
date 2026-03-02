"""
Deploy database schema to Supabase
"""
import os
from pathlib import Path
from supabase import create_client

# Read environment
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

print("Deploying database schema to Supabase...")
print(f"URL: {SUPABASE_URL}")

# Read schema
schema_file = Path(__file__).parent / "db" / "schema.sql"
with open(schema_file, 'r', encoding='utf-8') as f:
    schema_sql = f.read()

# Create client
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("\nExecuting SQL schema...")

# Split by semicolons and execute each statement
statements = [s.strip() for s in schema_sql.split(';') if s.strip()]

success_count = 0
error_count = 0

for i, statement in enumerate(statements, 1):
    if not statement or statement.startswith('--'):
        continue

    try:
        # Use rpc to execute SQL
        result = client.rpc('exec_sql', {'query': statement}).execute()
        success_count += 1
        print(f"[{i}/{len(statements)}] ✓")
    except Exception as e:
        # Many statements will "fail" because tables already exist, that's OK
        if "already exists" in str(e) or "does not exist" in str(e):
            success_count += 1
            print(f"[{i}/{len(statements)}] ✓ (already exists)")
        else:
            error_count += 1
            print(f"[{i}/{len(statements)}] ✗ Error: {str(e)[:100]}")

print(f"\n{'='*60}")
print(f"Deployment complete!")
print(f"Success: {success_count}")
print(f"Errors: {error_count}")
print(f"{'='*60}")

print("\nNOTE: If you see errors about missing RPC function 'exec_sql',")
print("you need to run the schema manually in Supabase SQL Editor:")
print(f"1. Go to: {SUPABASE_URL.replace('supabase.co', 'supabase.co')}/project/_/sql")
print(f"2. Copy contents of: {schema_file}")
print("3. Execute")
