# Feature Implementation Plan: fix-adk-sql-schema-error

## 📋 Todo Checklist
- [x] Verify PostgreSQL is running and accessible
- [x] Check if `tickets-db` database exists
- [x] Verify the database schema for the `events` table
- [x] Apply the schema migration to add missing metadata columns (`usage_metadata`, `citation_metadata`)
- [x] Verify all metadata columns exist
- [x] Test the `/agent/interact/` endpoint to confirm the fix ✅ **WORKING**
- [x] Final Review and Testing

## ✅ Resolution Status: **FIXED**
The SQL schema error has been successfully resolved. The `/agent/interact/` endpoint is now working correctly with `google-adk==1.17.0`.

## 🔍 Analysis & Investigation

### Codebase Structure
- `adk_bug_ticket_agent/views.py`: Contains the `interact_with_agent` view, which is the entry point for the failing API call.
- `adk_bug_ticket_agent/agent.py`: Initializes the `DatabaseSessionService` from `google-adk`, which is responsible for database interactions.
- `sql/data.sql`: Contains the SQL statements to set up the database, including the `tickets` table and a block to alter the `events` table.
- `pyproject.toml`: Confirms the use of `google-adk==1.17.0`.

### Current Architecture
The application is a Django-based web service. The `/agent/interact/` endpoint uses the `google-adk` library to manage agent conversations. The `DatabaseSessionService` is configured to use a PostgreSQL database to persist conversation history in an `events` table. The error `psycopg2.errors.UndefinedColumn: column events.custom_metadata does not exist` indicates that the `events` table schema is out of sync with the expectations of `google-adk==1.17.0`.

### Dependencies & Integration Points
The core issue lies in the integration between the Django application and the `google-adk` library, specifically its `DatabaseSessionService` and the underlying PostgreSQL database schema. The update to `google-adk==1.17.0` introduced requirements for THREE new JSONB columns in the `events` table:
- `custom_metadata`
- `usage_metadata`
- `citation_metadata`

### Considerations & Challenges
The main challenges were:
1. **Incomplete migration**: The `sql/data.sql` file only adds `custom_metadata`, but not `usage_metadata` or `citation_metadata`.
2. **Table ownership**: The `events` table is auto-created by ADK's `DatabaseSessionService`, not by application SQL scripts.
3. **Local environment differences**: The `sql/data.sql` includes Cloud SQL-specific extensions that won't work locally.
4. **Solution**: Create a separate, idempotent migration script (`sql/add_metadata_columns.sql`) that adds all missing metadata columns safely.

## 📝 Implementation Plan

### Prerequisites
- A running local PostgreSQL instance (PostgreSQL 15+ recommended).
- The database `tickets-db` must exist (default: `postgresql://postgres:admin@localhost:5432/tickets-db`).
- PostgreSQL binaries in PATH (on macOS with Homebrew: `/opt/homebrew/opt/postgresql@15/bin`).

### Root Cause Analysis
The error occurs because `google-adk==1.17.0` requires additional JSONB columns in the `events` table:
- `custom_metadata` (may already exist if table was created recently)
- `usage_metadata` (likely missing)
- `citation_metadata` (likely missing)

**Important**: The `events` table is auto-created by ADK's `DatabaseSessionService`, not by `sql/data.sql`. The `sql/data.sql` file creates the `tickets` table and attempts to add `custom_metadata` to `events`, but doesn't handle the other metadata columns.

### When Is This Migration Needed?

**Migration Required** (This was your case):
- You have an existing `events` table created by `google-adk` versions older than 1.17.0
- You upgraded from `google-adk` 1.2.1 → 1.6.1 → 1.9.0 → 1.17.0
- The old table schema is missing the new columns that 1.17.0 expects
- **Solution**: Run the migration script to add missing columns

**Migration NOT Required**:
- Fresh installation starting with `google-adk==1.17.0` from the beginning
- ADK's `DatabaseSessionService` creates the `events` table with all required columns automatically
- No schema mismatch = no errors

### Step-by-Step Implementation
1. **Verify PostgreSQL is Running**:
   ```bash
   # On macOS with Homebrew
   /opt/homebrew/opt/postgresql@15/bin/psql -U postgres -d postgres -c "SELECT version();"
   ```

2. **Check Database and Table Exist**:
   ```bash
   /opt/homebrew/opt/postgresql@15/bin/psql -U postgres -d postgres -c "\l tickets-db"
   /opt/homebrew/opt/postgresql@15/bin/psql -U postgres -d tickets-db -c "\d events"
   ```

3. **Apply the Comprehensive Migration**:
   - Use the new migration script `sql/add_metadata_columns.sql` which adds all missing metadata columns.
   - **Migration Script Content** (`sql/add_metadata_columns.sql`):
     ```sql
     -- Migration script to add missing metadata columns for google-adk 1.17.0
     -- This script is idempotent and can be run multiple times safely

     DO $$
     BEGIN
         -- Add usage_metadata column if it doesn't exist
         IF NOT EXISTS (
             SELECT FROM information_schema.columns
             WHERE table_name = 'events' AND column_name = 'usage_metadata'
         ) THEN
             ALTER TABLE events ADD COLUMN usage_metadata JSONB;
             RAISE NOTICE 'Added usage_metadata column';
         ELSE
             RAISE NOTICE 'usage_metadata column already exists';
         END IF;

         -- Add citation_metadata column if it doesn't exist
         IF NOT EXISTS (
             SELECT FROM information_schema.columns
             WHERE table_name = 'events' AND column_name = 'citation_metadata'
         ) THEN
             ALTER TABLE events ADD COLUMN citation_metadata JSONB;
             RAISE NOTICE 'Added citation_metadata column';
         ELSE
             RAISE NOTICE 'citation_metadata column already exists';
         END IF;
     END $$;
     ```
   - **Command to run**:
     ```bash
     /opt/homebrew/opt/postgresql@15/bin/psql -U postgres -d tickets-db -f sql/add_metadata_columns.sql
     ```
   - **Note**: This migration has also been integrated into `sql/data.sql` for future deployments.

4. **Verify the Schema Changes**:
   ```bash
   /opt/homebrew/opt/postgresql@15/bin/psql -U postgres -d tickets-db -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'events' AND column_name LIKE '%metadata%' ORDER BY column_name;"
   ```
   You should see: `citation_metadata`, `custom_metadata`, `grounding_metadata`, `usage_metadata`.

5. **Restart the Application**:
   - Stop and restart the Django development server to clear SQLAlchemy connection pools.
   ```bash
   python manage.py runserver
   # Or if using gunicorn:
   gunicorn web.wsgi:application
   ```

### Testing Strategy
1.  After applying the schema change and restarting the server, make a `POST` request to the `http://127.0.0.1:8000/agent/interact/` endpoint with a valid JSON payload.
2.  A successful test will result in a `200 OK` response from the server with the agent's reply, and no `sqlalchemy.exc.ProgrammingError` in the server logs.

## 🎯 Success Criteria
- The `POST` request to `/agent/interact/` completes successfully without any SQL-related errors.
- The application is fully functional with `google-adk==1.17.0`.

## 📁 Files Created/Modified

### Created Files
1. **`sql/add_metadata_columns.sql`**
   - Standalone migration script for adding missing metadata columns
   - Idempotent - safe to run multiple times
   - Can be used for quick fixes on existing databases

### Modified Files
1. **`sql/data.sql`**
   - Updated the migration block at the top to include `usage_metadata` and `citation_metadata`
   - Now handles all three metadata columns: `custom_metadata`, `usage_metadata`, `citation_metadata`
   - Safe for both fresh deployments and upgrades

2. **`plans/fix-adk-sql-schema-error.md`** (this file)
   - Comprehensive documentation of the issue, root cause, and solution
   - Step-by-step implementation guide
   - Clarification on when migration is needed vs. not needed

### Pending Changes (Uncommitted)
- `pyproject.toml`: `google-adk==1.9.0` → `google-adk==1.17.0` (not yet committed to git)
