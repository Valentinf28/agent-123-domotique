ALTER TABLE `installation_dossiers` ADD `solar_peak_watts` integer DEFAULT 0 NOT NULL;
ALTER TABLE `installation_dossiers` ADD `battery_capacity_wh` integer DEFAULT 0 NOT NULL;
ALTER TABLE `installation_dossiers` ADD `battery_reserve_percent` integer DEFAULT 25 NOT NULL;
ALTER TABLE `installation_dossiers` ADD `flexible_loads_json` text DEFAULT '[]' NOT NULL;
ALTER TABLE `installation_dossiers` ADD `predictive_control_enabled` integer DEFAULT false NOT NULL;

UPDATE `installation_dossiers`
SET
  `solar_peak_watts` = 9635,
  `battery_capacity_wh` = 15000,
  `flexible_loads_json` = '[{"id":"pac-piscine","name":"PAC piscine","category":"pool","icon":"≋","powerWatts":2000,"minimumRunMinutes":60,"priority":2,"enabled":true},{"id":"chauffe-eau","name":"Chauffe-eau","category":"hot_water","icon":"♨","powerWatts":2400,"minimumRunMinutes":120,"priority":1,"enabled":false},{"id":"recharge-vehicule","name":"Recharge véhicule","category":"vehicle","icon":"◇","powerWatts":7400,"minimumRunMinutes":120,"priority":3,"enabled":false},{"id":"filtration-piscine","name":"Filtration piscine","category":"filtration","icon":"≋","powerWatts":700,"minimumRunMinutes":120,"priority":4,"enabled":false}]'
WHERE `reference` IN ('DOSSIER-PILOTE', 'SHOWROOM-123');
