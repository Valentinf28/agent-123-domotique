CREATE TABLE `agent_boxes` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`public_id` text NOT NULL,
	`dossier_id` integer NOT NULL,
	`label` text DEFAULT 'Box domotique' NOT NULL,
	`token_hash` text NOT NULL,
	`ha_version` text,
	`inventory_count` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'enrolled' NOT NULL,
	`last_seen_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_boxes_public_id_idx` ON `agent_boxes` (`public_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `agent_boxes_token_hash_idx` ON `agent_boxes` (`token_hash`);--> statement-breakpoint
CREATE UNIQUE INDEX `agent_boxes_dossier_idx` ON `agent_boxes` (`dossier_id`);--> statement-breakpoint
CREATE TABLE `agent_enrollment_codes` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`public_id` text NOT NULL,
	`dossier_id` integer NOT NULL,
	`code_hash` text NOT NULL,
	`expires_at` text NOT NULL,
	`used_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_enrollment_codes_public_id_idx` ON `agent_enrollment_codes` (`public_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `agent_enrollment_codes_hash_idx` ON `agent_enrollment_codes` (`code_hash`);