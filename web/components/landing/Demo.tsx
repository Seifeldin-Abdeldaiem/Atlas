"use client";

import { useRef, useState, type KeyboardEvent } from "react";

import {
  duplicateValue,
  groupStock,
  groups,
  lookalikes,
  money,
  totals,
  type SampleGroup,
} from "./sample";

const TABS = [
  { id: "duplicates", label: "Duplicates", count: totals.groups },
  { id: "lookalikes", label: "Similar but different", count: lookalikes.length },
  { id: "stock", label: "Stock and value", count: null },
  { id: "file", label: "Clean file", count: null },
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
          <span className="mono">stores-catalogue.xlsx</span>
          <span className="muted">· 1,240 lines checked</span>
        </div>
        <span className="badge badge-warn">Example results</span>
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
        {tab === "lookalikes" && <Lookalikes />}
        {tab === "stock" && <StockValue />}
        {tab === "file" && <CleanFile />}
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
          <p className="muted">{group.reason}</p>
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
                <td>{r.name}</td>
                <td className="right num">{r.stock}</td>
                <td className="right num">{money(r.cost)}</td>
                <td className="right">
                  {r.code === group.masterCode ? (
                    <span className="badge badge-neutral">Keep</span>
                  ) : (
                    <span className="lp-merge">Merge</span>
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

function Lookalikes() {
  return (
    <div className="lp-stack">
      <p className="muted lp-note">
        These look almost the same, but they are different parts. Atlas keeps them apart and tells you why.
      </p>
      {lookalikes.map((p) => (
        <article key={p.b.code} className="lp-pair">
          <div className="lp-pair-items">
            <div>
              <span className="mono muted">{p.a.code}</span>
              <strong>{p.a.name}</strong>
            </div>
            <span className="lp-neq" aria-label="is not the same as">
              ≠
            </span>
            <div>
              <span className="mono muted">{p.b.code}</span>
              <strong>{p.b.name}</strong>
            </div>
          </div>
          <p>
            <span className="badge badge-danger">{p.difference}</span> {p.detail}
          </p>
        </article>
      ))}
    </div>
  );
}

function StockValue() {
  return (
    <div className="lp-stack">
      <div className="lp-figures">
        <Figure value={String(totals.duplicateLines)} label="duplicate lines" />
        <Figure value={String(totals.unitsOnDuplicates)} label="units sitting on duplicate lines" />
        <Figure value={money(totals.valueOnDuplicates)} label="of stock on duplicate lines" />
      </div>
      <div className="table-wrap lp-bordered">
        <table className="grid">
          <thead>
            <tr>
              <th>Item</th>
              <th className="right">Lines</th>
              <th className="right">Total in stock</th>
              <th className="right">Value on duplicate lines</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id}>
                <td>{g.standardName}</td>
                <td className="right num">{g.rows.length}</td>
                <td className="right num">{groupStock(g)}</td>
                <td className="right num">{money(duplicateValue(g))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted lp-note">
        For example, you have {groupStock(groups[0])} of the SKF 6205-2RS bearing, not {groups[0].rows[0].stock}.
        Before reordering, check the total.
      </p>
    </div>
  );
}

function CleanFile() {
  const rows = groups.flatMap((g) =>
    g.rows.map((r) => ({ ...r, group: g.id, role: r.code === g.masterCode ? "master" : "duplicate", std: g.standardName })),
  );
  return (
    <div className="lp-stack">
      <p className="muted lp-note">
        You get your own file back, every row and column untouched, with Atlas&apos;s findings added on the right. Open
        it in Excel, filter, and import it back.
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
            {rows.map((r) => (
              <tr key={r.code}>
                <td className="mono">{r.code}</td>
                <td>
                  <span className="trunc">{r.name}</span>
                </td>
                <td className="mono lp-added">{r.group}</td>
                <td className="mono lp-added">{r.role}</td>
                <td className="lp-added">
                  <span className="trunc">{r.std}</span>
                </td>
              </tr>
            ))}
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
