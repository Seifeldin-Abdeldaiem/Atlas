"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Crumbs, FileErrorGlyph, Sep, Spinner, Steps } from "@/components/ui";
import {
  ApiError,
  downloadFrom,
  formatMoney,
  formatNumber,
  useApi,
  type AnalysisSummary,
  type Dataset,
  type DuplicateGroup,
  type ExportState,
  type ItemView,
  type PairView,
  type WorkspaceSettings,
} from "@/lib/api";

const POLL_MS = 1500;
const PAGE = 25;

const STAGES: Record<string, string> = {
  matching: "Comparing lines",
  ai_review: "Checking unclear pairs with AI",
};

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setDataset(await api<Dataset>(`/v1/datasets/${id}`));
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "We couldn't load these results.");
    }
  }, [api, id]);

  useEffect(() => {
    void load();
    api<WorkspaceSettings>("/v1/settings").then(setSettings).catch(() => setSettings(null));
  }, [load, api]);

  // Poll while the analysis runs or the download is being prepared.
  useEffect(() => {
    if (!dataset) return;
    const busy = dataset.status === "analysing" || dataset.export?.state === "building";
    if (!busy) return;
    const timer = setTimeout(() => void load(), POLL_MS);
    return () => clearTimeout(timer);
  }, [dataset, load]);

  async function start() {
    setStarting(true);
    setActionError(null);
    try {
      await api(`/v1/datasets/${id}/analysis`, { method: "POST" });
      await load();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn't start the analysis.");
    } finally {
      setStarting(false);
    }
  }

  function onSummary(summary: AnalysisSummary) {
    setDataset((d) => (d && d.analysis ? { ...d, analysis: { ...d.analysis, summary }, export: null } : d));
  }

  const title = dataset?.file.name ?? dataset?.name ?? "Dataset";
  const analysed = dataset?.status === "analysed";
  const summary = dataset?.analysis?.summary;
  const failed = dataset?.status === "ready" && dataset.analysis?.state === "failed";

  return (
    <>
      <header className="topbar">
        <Crumbs>
          <Link href="/datasets">Datasets</Link>
          <Sep />
          <Link href={`/datasets/${id}/preview`}>{title}</Link>
          <Sep />
          <span className="here">Results</span>
        </Crumbs>
        {analysed && (
          <button className="btn btn-secondary btn-sm" type="button" onClick={start} disabled={starting}>
            Run again
          </button>
        )}
      </header>

      <div className="page">
        <div className="page-title">
          <div>
            <h1 className="serif">{analysed ? "Duplicates found" : "Finding duplicates"}</h1>
            <p>
              {analysed
                ? "Check each group, keep the right line, and download your file with the results added."
                : "Atlas compares every line with the ones most like it. You can leave this page and come back."}
            </p>
          </div>
          <Steps current={analysed ? 4 : 3} />
        </div>

        {loadError && (
          <div className="panel state" role="alert">
            <h2>We couldn&apos;t load these results</h2>
            <p>{loadError}</p>
            <Link className="btn btn-secondary" href="/datasets">
              Back to datasets
            </Link>
          </div>
        )}

        {actionError && (
          <div className="panel notice-error" role="alert">
            {actionError}
          </div>
        )}

        {!loadError && !dataset && (
          <div className="panel state" aria-busy="true">
            <Spinner size={28} />
          </div>
        )}

        {dataset?.status === "analysing" && <Progress stage={dataset.analysis?.stage} progress={dataset.analysis?.progress ?? 0} />}

        {dataset && (dataset.status === "ready" || dataset.status === "blocked") && (
          <div className="panel state" role={failed ? "alert" : undefined}>
            {failed ? <FileErrorGlyph /> : null}
            <h2>{failed ? "The analysis didn't finish" : "Not analysed yet"}</h2>
            <p>{failed ? dataset.analysis?.error?.message : "Start the analysis to find duplicate lines in this file."}</p>
            {dataset.kind === "catalogue" && dataset.status === "ready" ? (
              <button className="btn btn-primary" type="button" onClick={start} disabled={starting}>
                {failed ? "Try again" : "Start analysis"}
              </button>
            ) : (
              <Link className="btn btn-secondary" href={`/datasets/${id}/preview`}>
                Back to check data
              </Link>
            )}
          </div>
        )}

        {analysed && summary && (
          <>
            <Headline summary={summary} />
            <AiNote summary={summary} settings={settings} />
            <Results datasetId={id} summary={summary} currency={summary.stock?.currency ?? null} onSummary={onSummary} onError={setActionError} />
          </>
        )}
      </div>

      {analysed && dataset && <ExportBar datasetId={id} state={dataset.export} reload={load} />}
    </>
  );
}

function Progress({ stage, progress }: { stage?: string; progress: number }) {
  const pct = Math.max(5, Math.round(progress * 100));
  return (
    <div className="panel state" aria-live="polite" aria-busy="true">
      <Spinner size={28} />
      <h2>{(stage && STAGES[stage]) || "Getting ready"}</h2>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Analysis progress">
        <div style={{ width: `${pct}%` }} />
      </div>
      <p>Large catalogues take a minute or two. Checking unclear pairs with AI can take a few minutes more.</p>
    </div>
  );
}

function Headline({ summary }: { summary: AnalysisSummary }) {
  const stock = summary.stock;
  return (
    <div className="panel facts">
      <div>
        <span className="label">Duplicate lines</span>
        <span className="fact-big num">{formatNumber(summary.duplicate_lines)}</span>
        <span className="label" style={{ fontWeight: 400 }}>
          in {formatNumber(summary.groups)} {summary.groups === 1 ? "group" : "groups"} · {formatNumber(summary.items)} lines checked
        </span>
      </div>
      <div>
        <span className="label">Units on duplicate lines</span>
        {stock?.units_on_duplicates != null ? (
          <span className="fact-big num">{formatNumber(stock.units_on_duplicates)}</span>
        ) : (
          <span className="muted">{stock?.has_stock ? "Units differ between lines" : "Add a stock column to see this"}</span>
        )}
      </div>
      <div>
        <span className="label">Value on duplicate lines</span>
        {stock?.value_on_duplicates != null ? (
          <span className="fact-big num">{formatMoney(stock.value_on_duplicates, stock.currency)}</span>
        ) : (
          <span className="muted">
            {stock?.mixed_currencies?.length ? `Costs are in ${stock.mixed_currencies.join(" and ")}` : "Add stock and cost columns to see this"}
          </span>
        )}
      </div>
      <div>
        <span className="label">Needs your review</span>
        <span className="fact-big num">{formatNumber(summary.needs_review)}</span>
        <span className="label" style={{ fontWeight: 400 }}>
          {formatNumber(summary.lookalikes)} look-alikes kept apart
        </span>
      </div>
    </div>
  );
}

function AiNote({ summary, settings }: { summary: AnalysisSummary; settings: WorkspaceSettings | null }) {
  let text: string;
  if (summary.ai === "on") {
    text = summary.ai_usage?.stopped
      ? "AI review stopped early because the AI service refused the key. Unclear pairs are listed under Needs review."
      : `AI checked ${formatNumber(summary.ai_reviewed)} unclear ${summary.ai_reviewed === 1 ? "pair" : "pairs"}.`;
  } else if (summary.ai === "off") {
    text = "AI review is turned off for this workspace, so unclear pairs are listed under Needs review.";
  } else {
    text = "AI review isn't set up on this server, so unclear pairs are listed under Needs review.";
  }
  return (
    <p className="muted ai-note">
      {text}{" "}
      {settings?.can_edit && <Link href="/settings">Settings</Link>}
    </p>
  );
}

// ---------------------------------------------------------------- tabs

type Tab = "duplicates" | "lookalikes" | "review";

function Results({
  datasetId,
  summary,
  currency,
  onSummary,
  onError,
}: {
  datasetId: string;
  summary: AnalysisSummary;
  currency: string | null;
  onSummary: (s: AnalysisSummary) => void;
  onError: (message: string | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("duplicates");
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "duplicates", label: "Duplicates", count: summary.groups },
    { id: "lookalikes", label: "Similar but different", count: summary.lookalikes },
    { id: "review", label: "Needs review", count: summary.needs_review },
  ];

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const i = tabs.findIndex((t) => t.id === tab);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const j = (next + tabs.length) % tabs.length;
    setTab(tabs[j].id);
    refs.current[j]?.focus();
  }

  return (
    <section className="panel">
      <div className="tabs" role="tablist" aria-label="Results" onKeyDown={onKey}>
        {tabs.map((t, i) => (
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
            className="tab"
            type="button"
            onClick={() => setTab(t.id)}
          >
            {t.label}
            <span className="tab-count num">{formatNumber(t.count)}</span>
          </button>
        ))}
      </div>
      <div className="tab-body" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "duplicates" && <GroupList datasetId={datasetId} currency={currency} onSummary={onSummary} onError={onError} />}
        {tab === "lookalikes" && <PairList kind="lookalike" datasetId={datasetId} currency={currency} onSummary={onSummary} onError={onError} />}
        {tab === "review" && <PairList kind="review" datasetId={datasetId} currency={currency} onSummary={onSummary} onError={onError} />}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- duplicate groups

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "medium", label: "Please check" },
  { value: "high", label: "High confidence" },
  { value: "reviewed", label: "Reviewed" },
];

function GroupList({
  datasetId,
  currency,
  onSummary,
  onError,
}: {
  datasetId: string;
  currency: string | null;
  onSummary: (s: AnalysisSummary) => void;
  onError: (message: string | null) => void;
}) {
  const api = useApi();
  const [filter, setFilter] = useState("");
  const [groups, setGroups] = useState<DuplicateGroup[] | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchPage = useCallback(
    async (offset: number, limit: number) => {
      const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (filter) q.set("confidence", filter);
      return api<{ total: number; groups: DuplicateGroup[] }>(`/v1/datasets/${datasetId}/groups?${q}`);
    },
    [api, datasetId, filter],
  );

  useEffect(() => {
    let active = true;
    setGroups(null);
    fetchPage(0, PAGE)
      .then((page) => {
        if (!active) return;
        setGroups(page.groups);
        setTotal(page.total);
      })
      .catch((e: unknown) => active && onError(e instanceof ApiError ? e.message : "We couldn't load the groups."));
    return () => {
      active = false;
    };
  }, [fetchPage, onError]);

  async function more() {
    if (!groups) return;
    const page = await fetchPage(groups.length, PAGE);
    setGroups([...groups, ...page.groups]);
    setTotal(page.total);
  }

  async function act(group: DuplicateGroup, action: string, row?: number) {
    setBusy(group.id);
    onError(null);
    try {
      const res = await api<{ summary: AnalysisSummary }>(`/v1/datasets/${datasetId}/groups/${group.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, row_number: row ?? null }),
      });
      onSummary(res.summary);
      const page = await fetchPage(0, Math.max(PAGE, groups?.length ?? PAGE));
      setGroups(page.groups);
      setTotal(page.total);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "We couldn't save that change.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Show">
        {FILTERS.map((f) => (
          <button key={f.value} type="button" className="chip" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
            {f.label}
          </button>
        ))}
      </div>
      {groups === null && <p className="muted">Loading…</p>}
      {groups !== null && groups.length === 0 && (
        <div className="empty-note">
          <strong>{filter ? "Nothing here" : "No duplicates found"}</strong>
          <span className="muted">{filter ? "Try another filter." : "Every line in this file looks unique. Check Needs review for anything Atlas wasn't sure about."}</span>
        </div>
      )}
      {groups?.map((g) => (
        <GroupCard key={g.id} group={g} currency={currency} busy={busy === g.id} onAction={(action, row) => act(g, action, row)} />
      ))}
      {groups && groups.length < total && (
        <button className="btn btn-secondary more" type="button" onClick={more}>
          Show more ({formatNumber(total - groups.length)} left)
        </button>
      )}
    </div>
  );
}

const CONFIDENCE: Record<DuplicateGroup["confidence"], { label: string; className: string }> = {
  high: { label: "High confidence", className: "badge badge-ok" },
  medium: { label: "Please check", className: "badge badge-warn" },
  reviewed: { label: "Reviewed", className: "badge badge-run" },
};

function GroupCard({
  group,
  currency,
  busy,
  onAction,
}: {
  group: DuplicateGroup;
  currency: string | null;
  busy: boolean;
  onAction: (action: string, row?: number) => void;
}) {
  const c = CONFIDENCE[group.confidence];
  const figures = [
    group.stock_total == null
      ? null
      : group.stock_total
        ? `${formatNumber(group.stock_total)} in stock across ${group.members.length} lines`
        : `No stock across ${group.members.length} lines`,
    group.value_on_duplicates ? `${formatMoney(group.value_on_duplicates, currency)} on duplicate lines` : null,
    group.cost_low != null && group.cost_high != null && group.cost_high > group.cost_low
      ? `unit cost ${formatMoney(group.cost_low, currency)} to ${formatMoney(group.cost_high, currency)}`
      : null,
  ].filter(Boolean);

  return (
    <article className="group-card" aria-busy={busy}>
      <header className="group-head">
        <div>
          <h3>{group.name_standard || group.members[0]?.name || group.id}</h3>
          <p className="muted">
            <span className="mono">{group.id}</span> · {group.reasons[0]}
          </p>
          {figures.length > 0 && <p className="group-figures num">{figures.join(" · ")}</p>}
        </div>
        <span className={c.className}>{c.label}</span>
      </header>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th>Code</th>
              <th>As written in your file</th>
              <th>Part</th>
              <th className="right">Stock</th>
              <th className="right">Unit cost</th>
              <th className="right">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {group.members.map((m) => (
              <tr key={m.row_number}>
                <td className="mono">{m.item_code || `Row ${m.row_number}`}</td>
                <td>
                  <span className="trunc">{m.name}</span>
                </td>
                <td className="mono nowrap">{m.part_number}</td>
                <td className="right num">{formatNumber(m.stock)}</td>
                <td className="right num">{formatMoney(m.unit_cost, m.currency || currency)}</td>
                <td className="right row-actions">
                  {m.role === "master" ? (
                    <span className="badge badge-neutral">Keep</span>
                  ) : (
                    <>
                      <button className="btn btn-ghost btn-sm" type="button" disabled={busy} onClick={() => onAction("set_master", m.row_number)}>
                        Keep this
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        type="button"
                        disabled={busy}
                        onClick={() => onAction("remove_row", m.row_number)}
                        aria-label={`Remove ${m.item_code || `row ${m.row_number}`} from this group`}
                      >
                        Remove
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="group-actions">
        {group.confidence !== "reviewed" && (
          <button className="btn btn-primary btn-sm" type="button" disabled={busy} onClick={() => onAction("approve")}>
            Confirm group
          </button>
        )}
        <button className="btn btn-secondary btn-sm" type="button" disabled={busy} onClick={() => onAction("reject")}>
          Not duplicates
        </button>
      </footer>
    </article>
  );
}

// ---------------------------------------------------------------- pairs

function PairList({
  kind,
  datasetId,
  currency,
  onSummary,
  onError,
}: {
  kind: "lookalike" | "review";
  datasetId: string;
  currency: string | null;
  onSummary: (s: AnalysisSummary) => void;
  onError: (message: string | null) => void;
}) {
  const api = useApi();
  const [pairs, setPairs] = useState<PairView[] | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchPage = useCallback(
    (offset: number, limit: number) => api<{ total: number; pairs: PairView[] }>(`/v1/datasets/${datasetId}/pairs?kind=${kind}&limit=${limit}&offset=${offset}`),
    [api, datasetId, kind],
  );

  useEffect(() => {
    let active = true;
    fetchPage(0, PAGE)
      .then((page) => {
        if (!active) return;
        setPairs(page.pairs);
        setTotal(page.total);
      })
      .catch((e: unknown) => active && onError(e instanceof ApiError ? e.message : "We couldn't load this list."));
    return () => {
      active = false;
    };
  }, [fetchPage, onError]);

  async function act(pair: PairView, verdict: "same" | "different") {
    const key = `${pair.a.row_number}-${pair.b.row_number}`;
    setBusy(key);
    onError(null);
    try {
      const res = await api<{ summary: AnalysisSummary }>(`/v1/datasets/${datasetId}/pairs/review`, {
        method: "POST",
        body: JSON.stringify({ row_a: pair.a.row_number, row_b: pair.b.row_number, verdict }),
      });
      onSummary(res.summary);
      setPairs((list) => list?.filter((p) => p !== pair) ?? null);
      setTotal((t) => t - 1);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "We couldn't save that change.");
    } finally {
      setBusy(null);
    }
  }

  const intro =
    kind === "lookalike"
      ? "These look almost the same but Atlas found a real difference, so it kept them apart. If two of them are in fact the same item, say so."
      : "Atlas couldn't tell whether these are the same item. Decide each one; your answer is kept if you run the analysis again.";

  return (
    <div className="stack">
      <p className="muted note">{intro}</p>
      {pairs === null && <p className="muted">Loading…</p>}
      {pairs !== null && pairs.length === 0 && (
        <div className="empty-note">
          <strong>{kind === "lookalike" ? "No look-alikes" : "Nothing to review"}</strong>
          <span className="muted">{kind === "lookalike" ? "No near misses were found in this file." : "Atlas was sure about every pair it compared."}</span>
        </div>
      )}
      {pairs?.map((p) => {
        const key = `${p.a.row_number}-${p.b.row_number}`;
        return (
          <article key={key} className="pair-card" aria-busy={busy === key}>
            <div className="pair-items">
              <PairItem item={p.a} currency={currency} />
              <span className="neq" aria-hidden="true">
                {kind === "lookalike" ? "≠" : "?"}
              </span>
              <PairItem item={p.b} currency={currency} />
            </div>
            <p className="pair-detail">
              {p.source === "ai" && <span className="badge badge-neutral">AI</span>} {p.detail}
            </p>
            <div className="pair-actions">
              {kind === "review" ? (
                <>
                  <button className="btn btn-primary btn-sm" type="button" disabled={busy === key} onClick={() => act(p, "same")}>
                    Same item
                  </button>
                  <button className="btn btn-secondary btn-sm" type="button" disabled={busy === key} onClick={() => act(p, "different")}>
                    Different items
                  </button>
                </>
              ) : (
                <>
                  <button className="btn btn-secondary btn-sm" type="button" disabled={busy === key} onClick={() => act(p, "different")}>
                    Agree, they&apos;re different
                  </button>
                  <button className="btn btn-ghost btn-sm" type="button" disabled={busy === key} onClick={() => act(p, "same")}>
                    They&apos;re the same item
                  </button>
                </>
              )}
            </div>
          </article>
        );
      })}
      {pairs && pairs.length < total && (
        <button
          className="btn btn-secondary more"
          type="button"
          onClick={async () => {
            const page = await fetchPage(pairs.length, PAGE);
            setPairs([...pairs, ...page.pairs]);
            setTotal(page.total);
          }}
        >
          Show more ({formatNumber(total - pairs.length)} left)
        </button>
      )}
    </div>
  );
}

function PairItem({ item, currency }: { item: ItemView; currency: string | null }) {
  const facts = [item.brand, item.part_number, item.stock != null ? `${formatNumber(item.stock)} in stock` : null, item.unit_cost != null ? formatMoney(item.unit_cost, item.currency || currency) : null].filter(Boolean);
  return (
    <div className="pair-item">
      <span className="mono muted">{item.item_code || `Row ${item.row_number}`}</span>
      <strong>{item.name}</strong>
      {facts.length > 0 && <span className="label" style={{ fontWeight: 400 }}>{facts.join(" · ")}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- download

function ExportBar({ datasetId, state, reload }: { datasetId: string; state: ExportState; reload: () => Promise<void> }) {
  const api = useApi();
  const { getToken } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const wanted = useRef(false);

  const download = useCallback(async () => {
    setDownloading(true);
    setError(null);
    try {
      await downloadFrom(await getToken(), `/v1/datasets/${datasetId}/export/download`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The download didn't start. Try again.");
    } finally {
      setDownloading(false);
    }
  }, [datasetId, getToken]);

  // Start the download by itself once a requested file is ready.
  useEffect(() => {
    if (wanted.current && state?.state === "ready") {
      wanted.current = false;
      void download();
    }
  }, [state, download]);

  async function prepare() {
    setError(null);
    wanted.current = true;
    try {
      await api(`/v1/datasets/${datasetId}/export`, { method: "POST" });
      await reload();
    } catch (e) {
      wanted.current = false;
      setError(e instanceof ApiError ? e.message : "We couldn't prepare your file.");
    }
  }

  const expires = state?.file?.expires_at ? new Date(state.file.expires_at).toLocaleDateString("en-GB", { day: "numeric", month: "long" }) : null;

  return (
    <footer className="footer-bar">
      <div>
        <div style={{ fontWeight: 500 }}>Your file with the results added</div>
        <div className="muted" style={{ fontSize: 13 }} aria-live="polite">
          {error ??
            (state?.state === "building"
              ? "Preparing your file…"
              : state?.state === "failed"
                ? state.error?.message
                : state?.state === "ready"
                  ? `${state.file?.name}, available until ${expires}`
                  : "Every row and column as uploaded, with the group, the line to keep and the reason added on the right.")}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {state?.state === "ready" ? (
          <button className="btn btn-primary" type="button" onClick={download} disabled={downloading}>
            {downloading ? "Downloading…" : "Download"}
          </button>
        ) : (
          <button className="btn btn-primary" type="button" onClick={prepare} disabled={state?.state === "building"}>
            {state?.state === "building" ? "Preparing…" : "Download results"}
          </button>
        )}
      </div>
    </footer>
  );
}
