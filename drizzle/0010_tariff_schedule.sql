ALTER TABLE installation_dossiers ADD COLUMN tariff_plan text NOT NULL DEFAULT 'base';
ALTER TABLE installation_dossiers ADD COLUMN off_peak_periods_json text NOT NULL DEFAULT '[]';
