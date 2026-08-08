ALTER TABLE `installation_dossiers` ADD `tariff_plan` text DEFAULT 'base' NOT NULL;
ALTER TABLE `installation_dossiers` ADD `off_peak_periods_json` text DEFAULT '[]' NOT NULL;
ALTER TABLE `installation_dossiers` ADD `energy_tariff_json` text DEFAULT '{}' NOT NULL;
