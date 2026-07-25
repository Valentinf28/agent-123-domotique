import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const installationDossiers = sqliteTable("installation_dossiers", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  publicId: text("public_id").notNull(),
  reference: text("reference").notNull(),
  customerName: text("customer_name").notNull(),
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
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("planned_devices_public_id_idx").on(table.publicId),
  uniqueIndex("planned_devices_dossier_catalog_room_idx").on(table.dossierId, table.catalogId, table.room),
]);
