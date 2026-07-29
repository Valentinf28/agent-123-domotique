ALTER TABLE `installation_dossiers` ADD `relay_house_id` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `subscription_status` text DEFAULT 'not_started' NOT NULL;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `subscription_price_cents` integer DEFAULT 790 NOT NULL;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `subscription_interval` text DEFAULT 'monthly' NOT NULL;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `trial_started_at` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `trial_ends_at` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `grace_ends_at` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `subscription_started_at` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `subscription_ends_at` text;
--> statement-breakpoint
UPDATE `installation_dossiers` SET `relay_house_id` = `public_id` WHERE `relay_house_id` IS NULL;
--> statement-breakpoint
CREATE UNIQUE INDEX `installation_dossiers_relay_house_id_idx` ON `installation_dossiers` (`relay_house_id`);
