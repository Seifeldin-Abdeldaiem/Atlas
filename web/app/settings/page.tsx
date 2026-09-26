"use client";

import { useEffect, useState } from "react";

import { Crumbs } from "@/components/ui";
import { ApiError, useApi, type WorkspaceSettings } from "@/lib/api";

const CURRENCIES = ["GBP", "EUR", "USD", "AED", "SAR", "EGP", "QAR", "KWD", "OMR", "BHD", "JOD"];

export default function SettingsPage() {
  const api = useApi();
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<WorkspaceSettings>("/v1/settings")
      .then(setSettings)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "We couldn't load the settings."));
  }, [api]);

  async function save(change: Partial<Pick<WorkspaceSettings, "ai_review" | "currency">>) {
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      setSettings(await api<WorkspaceSettings>("/v1/settings", { method: "PUT", body: JSON.stringify(change) }));
      setSaved("Saved. It applies the next time you run an analysis.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't save that.");
    } finally {
      setSaving(false);
    }
  }

  const locked = !settings?.can_edit || saving;

  return (
    <>
      <header className="topbar">
        <Crumbs>
          <span className="here">Settings</span>
        </Crumbs>
      </header>
      <div className="page">
        <div className="page-title">
          <div>
            <h1 className="serif">Workspace settings</h1>
            <p>These apply to everyone in this workspace. {settings && !settings.can_edit && "Only workspace admins can change them."}</p>
          </div>
        </div>

        {error && (
          <div className="panel notice-error" role="alert">
            {error}
          </div>
        )}
        {saved && (
          <div className="panel notice-ok" role="status">
            {saved}
          </div>
        )}

        {settings && (
          <>
            <section className="panel setting">
              <div>
                <h2>AI review of unclear pairs</h2>
                <p className="muted">
                  When Atlas can&apos;t tell whether two lines are the same item (for example one written in English and one in Arabic), it can ask
                  an AI model. Only the cleaned name, brand, part number, variant, kind of product and sizes are sent; never stock, cost,
                  supplier or your other columns. The AI provider doesn&apos;t train on them. Turned off, those pairs stay under Needs review.
                </p>
                {!settings.ai_available && (
                  <p className="label" style={{ fontWeight: 400, marginTop: 8 }}>
                    AI review isn&apos;t set up on this server yet, so this switch has no effect until it is.
                  </p>
                )}
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="AI review of unclear pairs"
                  checked={settings.ai_review}
                  disabled={locked}
                  onChange={(e) => save({ ai_review: e.target.checked })}
                />
                <span>{settings.ai_review ? "On" : "Off"}</span>
              </label>
            </section>

            <section className="panel setting">
              <div>
                <h2>Currency</h2>
                <p className="muted">Used for costs written without a currency symbol. Costs with a symbol (£, $, €) keep their own.</p>
              </div>
              <select
                className="select"
                aria-label="Currency"
                value={settings.currency}
                disabled={locked}
                onChange={(e) => save({ currency: e.target.value })}
              >
                {[...new Set([settings.currency, ...CURRENCIES])].map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </section>
          </>
        )}
      </div>
    </>
  );
}
