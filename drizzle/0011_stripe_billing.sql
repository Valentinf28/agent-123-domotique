ALTER TABLE `installation_dossiers` ADD `stripe_customer_id` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `stripe_subscription_id` text;
--> statement-breakpoint
ALTER TABLE `installation_dossiers` ADD `stripe_current_period_ends_at` text;
