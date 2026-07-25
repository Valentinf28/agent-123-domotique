import type { Metadata } from "next";
import LovelaceShell from "./shell";

export const metadata: Metadata = {
  title: "Tableau de bord",
  description: "Le tableau de bord sécurisé de votre maison.",
};

export default function MaMaisonPage() {
  return <LovelaceShell />;
}
