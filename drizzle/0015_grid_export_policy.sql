ALTER TABLE `installation_dossiers` ADD `allow_grid_export` integer DEFAULT true NOT NULL;
UPDATE `installation_dossiers` SET `allow_grid_export` = false WHERE `relay_house_id` = 'maison-valentin';
