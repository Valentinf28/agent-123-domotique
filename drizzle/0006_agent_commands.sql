CREATE TABLE `agent_commands` (
  `id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  `public_id` text NOT NULL,
  `dossier_id` integer NOT NULL,
  `action` text NOT NULL,
  `payload_json` text DEFAULT '{}' NOT NULL,
  `status` text DEFAULT 'queued' NOT NULL,
  `error` text,
  `created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  `delivered_at` text,
  `completed_at` text,
  FOREIGN KEY (`dossier_id`) REFERENCES `installation_dossiers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_commands_public_id_idx` ON `agent_commands` (`public_id`);
