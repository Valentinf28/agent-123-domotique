import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const installationDossiers = sqliteTable("installation_dossiers", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  relayHouseId: text("relay_house_id"),
  reference: text("reference").notNull(),
  customerName: text("customer_name").notNull(),
  enabledModules: text("enabled_modules").notNull().default('["home","solar","heating","access","vehicle"]'),
  status: text("status").notNull().default("preparation"),
  subscriptionStatus: text("subscription_status").notNull().default("not_started"),
  subscriptionPriceCents: integer("subscription_price_cents").notNull().default(990),
  subscriptionInterval: text("subscription_interval").notNull().default("monthly"),
  trialStartedAt: text("trial_started_at"),
  trialEndsAt: text("trial_ends_at"),
  graceEndsAt: text("grace_ends_at"),
  subscriptionStartedAt: text("subscription_started_at"),
  subscriptionEndsAt: text("subscription_ends_at"),
  stripeCustomerId: text("stripe_customer_id"),
  stripeSubscriptionId: text("stripe_subscription_id"),
  stripeCurrentPeriodEndsAt: text("stripe_current_period_ends_at"),
  solarPeakWatts: integer("solar_peak_watts").notNull().default(0),
  solarArraysJson: text("solar_arrays_json").notNull().default("[]"),
  batteryCapacityWh: integer("battery_capacity_wh").notNull().default(0),
  erpDossierId: integer("erp_dossier_id"),
  erpImportedAt: text("erp_imported_at"),
  customerAddress: text("customer_address"),
  batteryReservePercent: integer("battery_reserve_percent").notNull().default(25),
  allowGridExport: integer("allow_grid_export", { mode: "boolean" }).notNull().default(true),
  tariffPlan: text("tariff_plan").notNull().default("base"),
  basePriceMilliEurosPerKwh: integer("base_price_milli_euros_per_kwh"),
  peakPriceMilliEurosPerKwh: integer("peak_price_milli_euros_per_kwh"),
  offPeakPriceMilliEurosPerKwh: integer("off_peak_price_milli_euros_per_kwh"),
  exportPriceMilliEurosPerKwh: integer("export_price_milli_euros_per_kwh"),
  offPeakPeriodsJson: text("off_peak_periods_json").notNull().default("[]"),
  flexibleLoadsJson: text("flexible_loads_json").notNull().default("[]"),
  entityBindingsJson: text("entity_bindings_json").notNull().default("{}"),
  predictiveControlEnabled: integer("predictive_control_enabled", { mode: "boolean" }).notNull().default(false),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("installation_dossiers_public_id_idx").on(table.publicId),
  uniqueIndex("installation_dossiers_relay_house_id_idx").on(table.relayHouseId),
  uniqueIndex("installation_dossiers_erp_dossier_id_idx").on(table.erpDossierId),
]);

export const plannedDevices = sqliteTable("planned_devices", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  catalogId: text("catalog_id").notNull(),
  brand: text("brand").notNull(),
  model: text("model").notNull(),
  category: text("category").notNull(),
  protocol: text("protocol").notNull(),
  compatibilityLevel: text("compatibility_level").notNull(),
  connectionMethod: text("connection_method").notNull(),
  prerequisites: text("prerequisites").notNull().default(""),
  estimatedMinutes: integer("estimated_minutes").notNull().default(0),
  icon: text("icon").notNull().default("◇"),
  quantity: integer("quantity").notNull().default(1),
  room: text("room").notNull().default("Maison"),
  status: text("status").notNull().default("À préparer"),
  matchedEntityId: text("matched_entity_id"),
  matchedEntityName: text("matched_entity_name"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("planned_devices_public_id_idx").on(table.publicId),
  uniqueIndex("planned_devices_dossier_catalog_room_idx").on(table.dossierId, table.catalogId, table.room),
]);

export const agentEnrollmentCodes = sqliteTable("agent_enrollment_codes", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  codeHash: text("code_hash").notNull(),
  expiresAt: text("expires_at").notNull(),
  usedAt: text("used_at"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("agent_enrollment_codes_public_id_idx").on(table.publicId),
  uniqueIndex("agent_enrollment_codes_hash_idx").on(table.codeHash),
]);

export const agentBoxes = sqliteTable("agent_boxes", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  label: text("label").notNull().default("Box domotique"),
  tokenHash: text("token_hash").notNull(),
  haVersion: text("ha_version"),
  inventoryCount: integer("inventory_count").notNull().default(0),
  inventoryJson: text("inventory_json").notNull().default("[]"),
  status: text("status").notNull().default("enrolled"),
  lastSeenAt: text("last_seen_at"),
  lastEnergySampleAt: text("last_energy_sample_at"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("agent_boxes_public_id_idx").on(table.publicId),
  uniqueIndex("agent_boxes_token_hash_idx").on(table.tokenHash),
  uniqueIndex("agent_boxes_dossier_idx").on(table.dossierId),
]);

export const energySnapshots = sqliteTable("energy_snapshots", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  bucket: text("bucket").notNull(),
  capturedAt: text("captured_at").notNull(),
  solarWatts: integer("solar_watts").notNull().default(0),
  homeWatts: integer("home_watts").notNull().default(0),
  gridWatts: integer("grid_watts").notNull().default(0),
  batteryPercent: integer("battery_percent").notNull().default(0),
  batteryWatts: integer("battery_watts").notNull().default(0),
  filtrationWatts: integer("filtration_watts").notNull().default(0),
  hotWaterWatts: integer("hot_water_watts").notNull().default(0),
  vehicleWatts: integer("vehicle_watts").notNull().default(0),
  dailyProductionWh: integer("daily_production_wh").notNull().default(0),
  dailyConsumptionWh: integer("daily_consumption_wh").notNull().default(0),
}, (table) => [
  uniqueIndex("energy_snapshots_dossier_bucket_idx").on(table.dossierId, table.bucket),
]);

export const assistantUsage = sqliteTable("assistant_usage", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  month: text("month").notNull(),
  requestCount: integer("request_count").notNull().default(0),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("assistant_usage_dossier_month_idx").on(table.dossierId, table.month),
]);

export const agentCommands = sqliteTable("agent_commands", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  action: text("action").notNull(),
  payloadJson: text("payload_json").notNull().default("{}"),
  status: text("status").notNull().default("queued"),
  error: text("error"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  deliveredAt: text("delivered_at"),
  completedAt: text("completed_at"),
}, (table) => [
  uniqueIndex("agent_commands_public_id_idx").on(table.publicId),
]);

export const mobilePairingCodes = sqliteTable("mobile_pairing_codes", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  dossierId: integer("dossier_id").notNull().references(() => installationDossiers.id, { onDelete: "cascade" }),
  codeHash: text("code_hash").notNull(),
  configurationTokenHash: text("configuration_token_hash"),
  expiresAt: text("expires_at").notNull(),
  usedAt: text("used_at"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("mobile_pairing_codes_public_id_idx").on(table.publicId),
  uniqueIndex("mobile_pairing_codes_hash_idx").on(table.codeHash),
  uniqueIndex("mobile_pairing_codes_configuration_token_hash_idx").on(table.configurationTokenHash),
]);
