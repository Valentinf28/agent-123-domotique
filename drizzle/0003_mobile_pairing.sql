CREATE TABLE `mobile_pairing_codes` (
  `id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  `public_id` text NOT NULL,
  `dossier_id` integer NOT NULL,
  `code_hash` text NOT NULL,
  `expires_at` text NOT NULL,
  `used_at` text,
  `created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);
CREATE UNIQUE INDEX `mobile_pairing_codes_public_id_idx` ON `mobile_pairing_codes` (`public_id`);
CREATE UNIQUE INDEX `mobile_pairing_codes_hash_idx` ON `mobile_pairing_codes` (`code_hash`);
