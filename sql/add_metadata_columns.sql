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
