ALTER TABLE `mobile_pairing_codes` ADD `configuration_token_hash` text;
CREATE UNIQUE INDEX `mobile_pairing_codes_configuration_token_hash_idx` ON `mobile_pairing_codes` (`configuration_token_hash`);
