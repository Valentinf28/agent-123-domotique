ALTER TABLE `installation_dossiers`
ADD `enabled_modules` text DEFAULT '["home","solar","heating","access","vehicle"]' NOT NULL;
