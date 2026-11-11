-- Read-only Supabase preflight for VolleyReview Saved Plays.
-- Run in the EXISTING project SQL editor. This changes nothing.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'plays'
  AND column_name IN (
    'id','dvsport_id','conference','match_date','match_name','play_type',
    'set_number','score','dvsport_play_number','dvsport_full_game_url',
    'dvsport_metadata','video_urls'
  )
ORDER BY ordinal_position;

-- Existing CHECK constraints, including any allowed play_type list.
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.plays'::regclass AND contype = 'c'
ORDER BY conname;

-- A unique index/constraint on dvsport_id is needed for safe upsert.
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'plays'
  AND indexdef ILIKE '%dvsport_id%'
ORDER BY indexname;

-- Check duplicates BEFORE adding an index if none exists.
SELECT dvsport_id, COUNT(*) AS duplicates
FROM public.plays
WHERE dvsport_id IS NOT NULL
GROUP BY dvsport_id
HAVING COUNT(*) > 1
ORDER BY duplicates DESC
LIMIT 25;
