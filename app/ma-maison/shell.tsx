"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type GatewaySession = { ready: boolean; dashboardPath?: string; message?: string };

export default function LovelaceShell() {
  const [session, setSession] = useState<GatewaySession | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    fetch("/api/lovelace/session", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        cache: "no-store",
      })
      .then((response) => response.json() as Promise<GatewaySession>)
      .then((payload) => { if (active) setSession(payload); })
      .catch(() => {
        if (active) setSession({ ready: false, message: "Votre maison est momentanément inaccessible." });
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  function refresh() {
    if (session?.ready && session.dashboardPath) setReloadKey((key) => key + 1);
    else {
      setLoading(true);
      fetch("/api/lovelace/session", { credentials: "same-origin", cache: "no-store" })
        .then((response) => response.json() as Promise<GatewaySession>)
        .then(setSession)
        .catch(() => setSession({ ready: false, message: "Votre maison est momentanément inaccessible." }))
        .finally(() => setLoading(false));
    }
  }

  return <main className="lovelace-shell">
    <header className="lovelace-web-header">
      <Link href="/" className="lovelace-back" aria-label="Retour au portail">‹</Link>
      <div><span>MA MAISON</span><h1>Tableau de bord</h1></div>
      <button onClick={refresh} aria-label="Actualiser le tableau de bord">↻</button>
    </header>
    <section className="lovelace-stage" aria-live="polite">
      {loading && <div className="lovelace-loading"><i /><h2>Chargement de votre maison…</h2><p>Connexion sécurisée au tableau de bord.</p></div>}
      {!loading && session?.ready && session.dashboardPath &&
        <iframe
          key={reloadKey}
          src={session.dashboardPath}
          title="Tableau de bord Ma Maison"
          allow="fullscreen"
        />}
      {!loading && !session?.ready && <div className="lovelace-error">
        <span>⌁</span><h2>Tableau de bord en préparation</h2>
        <p>{session?.message ?? "La passerelle sécurisée n’est pas encore disponible."}</p>
        <button onClick={refresh}>Réessayer</button><Link href="/">Retour au portail</Link>
      </div>}
    </section>
  </main>;
}
