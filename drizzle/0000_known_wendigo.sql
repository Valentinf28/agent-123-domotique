CREATE TABLE `installation_dossiers` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`public_id` text NOT NULL,
	`reference` text NOT NULL,
	`customer_name` text NOT NULL,
	`status` text DEFAULT 'preparation' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `installation_dossiers_public_id_idx` ON `installation_dossiers` (`public_id`);--> statement-breakpoint
CREATE TABLE `planned_devices` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`public_id` text NOT NULL,
	`dossier_id` integer NOT NULL,
	`catalog_id` text NOT NULL,
	`brand` text NOT NULL,
	`model` text NOT NULL,
	`category` text NOT NULL,
	`protocol` text NOT NULL,
	`compatibility_level` text NOT NULL,
	`connection_method` text NOT NULL,
	`prerequisites` text DEFAULT '' NOT NULL,
	`estimated_minutes` integer DEFAULT 0 NOT NULL,
	`icon` text DEFAULT '◇' NOT NULL,
	`quantity` integer DEFAULT 1 NOT NULL,
	`room` text DEFAULT 'Maison' NOT NULL,
	`status` text DEFAULT 'À préparer' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `planned_devices_public_id_idx` ON `planned_devices` (`public_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `planned_devices_dossier_catalog_room_idx` ON `planned_devices` (`dossier_id`,`catalog_id`,`room`);