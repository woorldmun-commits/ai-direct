ALTER TABLE sync_runs ADD COLUMN available_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE sync_runs ADD COLUMN period_to date;
ALTER TABLE sync_runs ADD COLUMN runner_managed boolean NOT NULL DEFAULT false;
CREATE INDEX sync_runs_runner_ready ON sync_runs(available_at,id)
  WHERE runner_managed AND status IN ('queued','running','waiting_report');
