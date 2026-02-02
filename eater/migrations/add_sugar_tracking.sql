-- Migration: Add sugar tracking to dishes_day table
-- Date: 2026-02-02
-- Purpose: Support "Add Sugar" feature

-- Add column for tracking added sugar in teaspoons
ALTER TABLE dishes_day 
ADD COLUMN IF NOT EXISTS added_sugar_tsp REAL DEFAULT 0.0;

-- Add comment
COMMENT ON COLUMN dishes_day.added_sugar_tsp IS 'Added sugar in teaspoons (1 tsp = ~5g = ~20 kcal)';

-- Create index for queries filtering by sugar
CREATE INDEX IF NOT EXISTS idx_dishes_day_sugar 
ON dishes_day(user_email, added_sugar_tsp) 
WHERE added_sugar_tsp > 0;

-- Verify migration
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'dishes_day' 
  AND column_name = 'added_sugar_tsp';
