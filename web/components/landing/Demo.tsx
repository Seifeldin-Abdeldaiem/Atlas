"use client";

import { useRef, useState, type KeyboardEvent } from "react";

import {
  allRows,
  groupStock,
  groups,
  lookalikes,
  money,
  totals,
  unsure,
  type SampleGroup,
  type SamplePair,
} from "./sample";

const TABS = [
  { id: "duplicates", label: "Duplicates", count: totals.groups },
  { id: "lookalikes", label: "Similar but different", count: lookalikes.length },
  { id: "review", label: "Needs review", count: unsure.length },
  { id: "file", label: "Your file", count: null },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Demo() {
  const [tab, setTab] = useState<TabId>("duplicates");
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const i = TABS.findIndex((t) => t.id === tab);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const j = (next + TABS.length) % TABS.length;
    setTab(TABS[j].id);
    refs.current[j]?.focus();
  }

  return (
    <div className="lp-demo">
      <div className="lp-demo-bar">
        <div className="lp-demo-file">
          <span className="lp-dot" aria-hidden="true" />
          <span className="mono">example-stock-list.xlsx</span>
          <span className="muted">· {totals.rows} rows checked</span>
        </div>
        <span className="badge badge-neutral">Example list, real results</span>
      </div>

      <div className="lp-figures">
        <Figure value={String(totals.duplicateLines)} label="extra rows for products already listed" />
        <Figure value={String(totals.unitsOnDuplicates)} label="units of stock sitting on those rows" />
        <Figure value={money(totals.valueOnDuplicates)} label="of stock on those rows, easy to buy again" />
      </div>

      <div className="lp-tabs" role="tablist" aria-label="Example results" onKeyDown={onKey}>
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className="lp-tab"
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.count !== null && <span className="lp-tab-count num">{t.count}</span>}
          </button>
        ))}
      </div>

      <div className="lp-demo-body" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "duplicates" && <Duplicates />}
        {tab === "lookalikes" && (
          <Pairs
            pairs={lookalikes}
            note="These look almost the same, but they are different parts. Atlas keeps them apart and tells you why."
            sign="≠"
          />
        )}
        {tab === "review" && (
          <Pairs
            pairs={unsure}
            note="When the names don't clearly describe the same product, Atlas doesn't guess. You decide with one click."
            sign="?"
            actions
          />
        )}
        {tab === "file" && <YourFile />}
      </div>
    </div>
  );
}

function Duplicates() {
  return (
    <div className="lp-stack">
      {groups.map((g) => (
        <GroupCard key={g.id} group={g} />
      ))}
    </div>
  );
}

function GroupCard({ group }: { group: SampleGroup }) {
  return (
    <article className="lp-group">
      <header className="lp-group-head">
        <div>
          <h4>{group.standardName}</h4>
          <p className="muted">
            <span className="mono">{group.id}</span> · {group.reason}
          </p>
          <p className="lp-group-figure">
            {groupStock(group)} in stock across {group.rows.length} rows
          </p>
        </div>
        <span className={`badge ${group.confidence === "High" ? "badge-ok" : "badge-run"}`}>
          {group.confidence} confidence
        </span>
      </header>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th>Code</th>
              <th>As written in your file</th>
              <th className="right">Stock</th>
              <th className="right">Unit cost</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {group.rows.map((r) => (
              <tr key={r.code}>
                <td className="mono">{r.code}</td>
                <td>
                  <bdi>{r.name}</bdi>
                </td>
                <td className="right num">{r.stock}</td>
                <td className="right num">{money(r.cost)}</td>
                <td className="right">
                  {r.code === group.masterCode ? (
                    <span className="badge badge-neutral">Keep</span>
                  ) : (
                    <span className="lp-merge">Duplicate</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function Pairs({ pairs, note, sign, actions = false }: { pairs: SamplePair[]; note: string; sign: string; actions?: boolean }) {
  return (
    <div className="lp-stack">
      <p className="muted lp-note">{note}</p>
      {pairs.map((p) => (
        <article key={`${p.a.code}-${p.b.code}`} className="lp-pair">
          <div className="lp-pair-items">
            <div>
              <span className="mono muted">{p.a.code}</span>
              <strong>{p.a.name}</strong>
            </div>
            <span className="lp-neq" aria-label={sign === "≠" ? "is not the same as" : "might be the same as"}>
              {sign}
            </span>
            <div>
              <span className="mono muted">{p.b.code}</span>
              <strong>{p.b.name}</strong>
            </div>
          </div>
          <p>
            <span className={`badge ${actions ? "badge-warn" : "badge-danger"}`}>{p.difference}</span> {p.detail}
          </p>
          {actions && (
            <div className="lp-pair-actions" aria-hidden="true">
              <span className="lp-art-btn lp-art-btn-primary">Same item</span>
              <span className="lp-art-btn">Different items</span>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function YourFile() {
  const info = new Map<string, { group: string; role: string; std: string }>();
  for (const g of groups) {
    for (const r of g.rows) info.set(r.code, { group: g.id, role: r.code === g.masterCode ? "master" : "duplicate", std: g.standardName });
  }
  for (const p of unsure) {
    for (const r of [p.a, p.b]) info.set(r.code, { group: "", role: "needs_review", std: "" });
  }
  return (
    <div className="lp-stack">
      <p className="muted lp-note">
        You get your own file back, every row and column untouched, with Atlas&apos;s answers added on the right. Open it
        in Excel, filter by group, and fix the rows you choose.
      </p>
      <div className="table-wrap lp-bordered">
        <table className="grid lp-file">
          <thead>
            <tr>
              <th>code</th>
              <th>name</th>
              <th className="lp-added">atlas_group</th>
              <th className="lp-added">atlas_role</th>
              <th className="lp-added">atlas_name_standard</th>
            </tr>
          </thead>
          <tbody>
            {allRows.map((r) => {
              const a = info.get(r.code) ?? { group: "", role: "unique", std: "" };
              return (
                <tr key={r.code}>
                  <td className="mono">{r.code}</td>
                  <td>
                    <span className="trunc">
                      <bdi>{r.name}</bdi>
                    </span>
                  </td>
                  <td className="mono lp-added">{a.group}</td>
                  <td className="mono lp-added">{a.role}</td>
                  <td className="lp-added">
                    <span className="trunc">{a.std}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="lp-figure">
      <span className="serif num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}
