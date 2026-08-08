ALTER TABLE `installation_dossiers` ADD `solar_arrays_json` text DEFAULT '[]' NOT NULL;
ALTER TABLE `installation_dossiers` ADD `erp_dossier_id` integer;
ALTER TABLE `installation_dossiers` ADD `erp_imported_at` text;
ALTER TABLE `installation_dossiers` ADD `customer_address` text;
CREATE UNIQUE INDEX `installation_dossiers_erp_dossier_id_idx` ON `installation_dossiers` (`erp_dossier_id`);
