-- Run once in the existing Supabase SQL Editor. Does not alter existing plays or video URLs.
-- Dynamically matches the existing public.plays.id type (UUID, bigint, etc.).
BEGIN;
DO $$
DECLARE play_id_type text;
BEGIN
  SELECT pg_catalog.format_type(a.atttypid, a.atttypmod)
    INTO play_id_type
  FROM pg_catalog.pg_attribute a
  JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'plays' AND a.attname = 'id'
        AND a.attnum > 0 AND NOT a.attisdropped;
  IF play_id_type IS NULL THEN
    RAISE EXCEPTION 'public.plays.id does not exist';
  END IF;
  EXECUTE format($create$
    CREATE TABLE IF NOT EXISTS public.play_comments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      play_id %s NOT NULL REFERENCES public.plays(id) ON DELETE CASCADE,
      author text NOT NULL DEFAULT 'Sheet reviewer',
      comment_text text NOT NULL CHECK (length(btrim(comment_text)) BETWEEN 1 AND 4000),
      tags text[] NOT NULL DEFAULT '{}'::text[],
      source text NOT NULL DEFAULT 'Google Sheets',
      created_at timestamptz NOT NULL DEFAULT now()
    )$create$, play_id_type);
END $$;
CREATE INDEX IF NOT EXISTS idx_play_comments_play_created
  ON public.play_comments (play_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_play_comments_created
  ON public.play_comments (created_at DESC);
ALTER TABLE public.play_comments ENABLE ROW LEVEL SECURITY;
-- No client grants/policies here: only your private service-role backend accesses comments.
COMMIT;
