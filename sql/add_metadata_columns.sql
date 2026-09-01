-- Migration script to add missing columns for google-adk v0 schema
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

    -- Add grounding_metadata column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'grounding_metadata'
    ) THEN
        ALTER TABLE events ADD COLUMN grounding_metadata JSONB;
        RAISE NOTICE 'Added grounding_metadata column';
    ELSE
        RAISE NOTICE 'grounding_metadata column already exists';
    END IF;

    -- Add custom_metadata column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'custom_metadata'
    ) THEN
        ALTER TABLE events ADD COLUMN custom_metadata JSONB;
        RAISE NOTICE 'Added custom_metadata column';
    ELSE
        RAISE NOTICE 'custom_metadata column already exists';
    END IF;

    -- Add input_transcription column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'input_transcription'
    ) THEN
        ALTER TABLE events ADD COLUMN input_transcription JSONB;
        RAISE NOTICE 'Added input_transcription column';
    ELSE
        RAISE NOTICE 'input_transcription column already exists';
    END IF;

    -- Add output_transcription column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'output_transcription'
    ) THEN
        ALTER TABLE events ADD COLUMN output_transcription JSONB;
        RAISE NOTICE 'Added output_transcription column';
    ELSE
        RAISE NOTICE 'output_transcription column already exists';
    END IF;

    -- Add partial column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'partial'
    ) THEN
        ALTER TABLE events ADD COLUMN partial BOOLEAN;
        RAISE NOTICE 'Added partial column';
    ELSE
        RAISE NOTICE 'partial column already exists';
    END IF;

    -- Add turn_complete column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'turn_complete'
    ) THEN
        ALTER TABLE events ADD COLUMN turn_complete BOOLEAN;
        RAISE NOTICE 'Added turn_complete column';
    ELSE
        RAISE NOTICE 'turn_complete column already exists';
    END IF;

    -- Add error_code column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'error_code'
    ) THEN
        ALTER TABLE events ADD COLUMN error_code VARCHAR(255);
        RAISE NOTICE 'Added error_code column';
    ELSE
        RAISE NOTICE 'error_code column already exists';
    END IF;

    -- Add error_message column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'error_message'
    ) THEN
        ALTER TABLE events ADD COLUMN error_message TEXT;
        RAISE NOTICE 'Added error_message column';
    ELSE
        RAISE NOTICE 'error_message column already exists';
    END IF;

    -- Add interrupted column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'interrupted'
    ) THEN
        ALTER TABLE events ADD COLUMN interrupted BOOLEAN;
        RAISE NOTICE 'Added interrupted column';
    ELSE
        RAISE NOTICE 'interrupted column already exists';
    END IF;

    -- Add long_running_tool_ids_json column if it doesn't exist
    IF NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'events' AND column_name = 'long_running_tool_ids_json'
    ) THEN
        ALTER TABLE events ADD COLUMN long_running_tool_ids_json TEXT;
        RAISE NOTICE 'Added long_running_tool_ids_json column';
    ELSE
        RAISE NOTICE 'long_running_tool_ids_json column already exists';
    END IF;
END $$;

