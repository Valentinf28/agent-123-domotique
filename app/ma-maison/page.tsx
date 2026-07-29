import type { Metadata } from "next";
import Portal from "../portal";

export const metadata: Metadata = {
  title: "Tableau de bord",
  description: "Le tableau de bord sécurisé de votre maison.",
};

export default function MaMaisonPage() {
  return <Portal customerOnly />;
}
