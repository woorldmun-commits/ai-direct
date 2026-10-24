-- Freeze the normalized strategy with the immutable statistical snapshot.
ALTER TABLE snapshots ADD COLUMN campaign_strategies jsonb NOT NULL DEFAULT '{}'
  CHECK (jsonb_typeof(campaign_strategies) = 'object');
