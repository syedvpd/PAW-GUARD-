# Supabase Database Security — Enabling Row Level Security (RLS)

This guide outlines how to fix the `UNRESTRICTED` security warning on your Supabase Table Editor.

---

## 🔒 The Security Risk
When Row Level Security (RLS) is disabled, any table is **unrestricted**. This means anyone possessing the project's public anon key (which is embedded in frontend clients) can read, write, or delete rows in those tables directly via the Supabase PostgREST API (`/rest/v1/`), bypassing your Python backend's authorization layers completely.

---

## 🛠️ Step-by-Step Fix

### Option 1: Execute SQL in Supabase SQL Editor (Recommended)

1. Open your **Supabase Dashboard**.
2. Go to the **SQL Editor** in the left sidebar.
3. Click **New Query**.
4. Copy and paste the following SQL script to enable RLS on **every table** in the public schema at once:

```sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'ALTER TABLE public.' || quote_ident(r.tablename) || ' ENABLE ROW LEVEL SECURITY;';
    END LOOP;
END $$;
```

5. Click **Run**.
6. Once complete, navigate back to your **Table Editor**. All `UNRESTRICTED` red warnings will disappear.

---

## 🔍 Why this works for the Python Backend
- The Python backend connects using the primary connection string as the owner (`postgres` superuser role).
- Superusers and the `service_role` **bypass RLS checks automatically**.
- This means your Python backend will continue to read/write data normally, while any direct requests from frontend clients using the `anon` key will be blocked.
