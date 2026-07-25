import type { Metadata } from "next";
import Portal from "./portal";

export const metadata: Metadata = {
  title: "Ma Maison — Portail domotique",
  description: "Pilotez simplement votre maison connectée.",
};

export default function Home() {
  return <Portal />;
}
