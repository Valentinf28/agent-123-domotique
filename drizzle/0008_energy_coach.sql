ALTER TABLE `agent_boxes` ADD `last_energy_sample_at` text;

CREATE TABLE `energy_snapshots` (
  `id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  `dossier_id` integer NOT NULL,
  `bucket` text NOT NULL,
  `captured_at` text NOT NULL,
  `solar_watts` integer DEFAULT 0 NOT NULL,
  `home_watts` integer DEFAULT 0 NOT NULL,
  `grid_watts` integer DEFAULT 0 NOT NULL,
  `battery_percent` integer DEFAULT 0 NOT NULL,
  `battery_watts` integer DEFAULT 0 NOT NULL,
  `filtration_watts` integer DEFAULT 0 NOT NULL,
  `hot_water_watts` integer DEFAULT 0 NOT NULL,
  `vehicle_watts` integer DEFAULT 0 NOT NULL,
  `daily_production_wh` integer DEFAULT 0 NOT NULL,
  `daily_consumption_wh` integer DEFAULT 0 NOT NULL,
  FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);

CREATE UNIQUE INDEX `energy_snapshots_dossier_bucket_idx`
ON `energy_snapshots` (`dossier_id`, `bucket`);

CREATE TABLE `assistant_usage` (
  `id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  `dossier_id` integer NOT NULL,
  `month` text NOT NULL,
  `request_count` integer DEFAULT 0 NOT NULL,
  `updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);

CREATE UNIQUE INDEX `assistant_usage_dossier_month_idx`
ON `assistant_usage` (`dossier_id`, `month`);

UPDATE `installation_dossiers`
SET `subscription_price_cents` = CASE
  WHEN `subscription_interval` = 'yearly' THEN 9900
  ELSE 990
END
WHERE `subscription_price_cents` IN (790, 7900);
