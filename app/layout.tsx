import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import "./globals.css";

const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Ma Maison", template: "%s · Ma Maison" },
  description: "Le portail simple et sécurisé de votre maison connectée.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: { title: "Ma Maison", description: "Votre maison, simplement.", images: ["/og.png"] },
  twitter: { card: "summary_large_image", title: "Ma Maison", description: "Votre maison, simplement.", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fr"><body className={manrope.variable}>{children}</body></html>;
}
