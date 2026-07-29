import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const installationDossiers = sqliteTable("installation_dossiers", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  reference: text("reference").notNull(),
  customerName: text("customer_name").notNull(),
  enabledModules: text("enabled_modules").notNull().default('["home","solar","heating","access","vehicle"]'),
  status: text("status").notNull().default("preparation"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("installation_dossiers_public_id_idx").on(table.publicId),
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
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("agent_boxes_public_id_idx").on(table.publicId),
  uniqueIndex("agent_boxes_token_hash_idx").on(table.tokenHash),
  uniqueIndex("agent_boxes_dossier_idx").on(table.dossierId),
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
  expiresAt: text("expires_at").notNull(),
  usedAt: text("used_at"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("mobile_pairing_codes_public_id_idx").on(table.publicId),
  uniqueIndex("mobile_pairing_codes_hash_idx").on(table.codeHash),
]);
