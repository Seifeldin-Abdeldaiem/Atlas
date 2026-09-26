"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Crumbs, ErrorIcon, FileErrorGlyph, InfoIcon, Sep, Spinner, Steps, WarnIcon } from "@/components/ui";
import { ApiError, FORMAT_NAMES, formatBytes, useApi, type Dataset, type Kind, type RowsPage, type Warning } from "@/lib/api";

const POLL_MS = 1500;
const PREVIEW_FIELDS: Record<Kind, string[]> = {
  tasks: ["external_id", "title", "project", "team", "status"],
  catalogue: ["item_code", "item_name", "part_number", "brand", "stock"],
};

export default function PreviewPage() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const router = useRouter();
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setDataset(await api<Dataset>(`/v1/datasets/${id}`));
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "We couldn’t load this dataset.");
    }
  }, [api, id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll only while the worker is reading the file.
  useEffect(() => {
    if (dataset?.status !== "parsing") return;
    const timer = setTimeout(() => void load(), POLL_MS);
    return () => clearTimeout(timer);
  }, [dataset, load]);

  async function changeMapping(column: string, field: string) {
    if (!dataset) return;
    const mapping: Record<string, string | null> = { ...dataset.mapping };
    for (const key of Object.keys(mapping)) if (mapping[key] === column) mapping[key] = null;
    if (field) mapping[field] = column; // moving a field off another column unmaps that column
    setSaving(true);
    setActionError(null);
    try {
      setDataset(await api<Dataset>(`/v1/datasets/${id}/mapping`, { method: "PUT", body: JSON.stringify({ mapping }) }));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn’t save that change.");
    } finally {
      setSaving(false);
    }
  }

  async function changeKind(kind: Kind) {
    if (!dataset || dataset.kind === kind) return;
    setSaving(true);
    setActionError(null);
    try {
      setDataset(await api<Dataset>(`/v1/datasets/${id}/kind`, { method: "PUT", body: JSON.stringify({ kind }) }));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn’t change the file type.");
    } finally {
      setSaving(false);
    }
  }

  async function chooseSheet(sheet: string) {
    setActionError(null);
    try {
      await api(`/v1/datasets/${id}/sheet`, { method: "POST", body: JSON.stringify({ sheet }) });
      await load();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn’t switch sheets.");
    }
  }

  async function startAnalysis() {
    setSaving(true);
    setActionError(null);
    try {
      await api(`/v1/datasets/${id}/analysis`, { method: "POST" });
      router.push(`/datasets/${id}/results`);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn’t start the analysis.");
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this dataset? Its file, tasks and report are removed permanently.")) return;
    try {
      await api(`/v1/datasets/${id}`, { method: "DELETE" });
      router.push("/datasets");
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "We couldn’t delete this dataset.");
    }
  }

  const title = dataset?.file.name ?? dataset?.name ?? "Dataset";

  return (
    <>
      <header className="topbar">
        <Crumbs>
          <Link href="/datasets">Datasets</Link>
          <Sep />
          <span className="here">{title}</span>
        </Crumbs>
        {dataset && dataset.status !== "parsing" && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-danger btn-sm" type="button" onClick={remove}>
              Delete dataset
            </button>
            <Link className="btn btn-secondary btn-sm" href="/datasets/new">
              Replace file
            </Link>
          </div>
        )}
      </header>

      <div className="page">
        <div className="page-title">
          <div>
            <h1 className="serif">Check your data</h1>
            <p>This is everything Atlas read from your file. Fix the column mapping if anything looks wrong.</p>
          </div>
          <Steps current={2} />
        </div>

        {loadError && (
          <div className="panel state" role="alert">
            <h2>We couldn’t load this dataset</h2>
            <p>{loadError}</p>
            <Link className="btn btn-secondary" href="/datasets">
              Back to datasets
            </Link>
          </div>
        )}

        {!loadError && (!dataset || dataset.status === "parsing") && (
          <div className="panel state" aria-live="polite" aria-busy="true">
            <Spinner size={28} />
            <h2>Reading your file</h2>
            <p>Checking its format, columns and rows. Large files take up to a minute.</p>
          </div>
        )}

        {dataset?.status === "failed" && (
          <div className="panel state" role="alert">
            <FileErrorGlyph />
            <h2>We can’t read this file</h2>
            <p>{dataset.error?.message ?? "Something went wrong while reading it."}</p>
            <Link className="btn btn-primary" href="/datasets/new">
              Choose another file
            </Link>
          </div>
        )}

        {actionError && (
          <div className="panel" role="alert" style={{ padding: "12px 20px", color: "var(--danger)", borderColor: "#e6b8ba" }}>
            {actionError}
          </div>
        )}

        {dataset && ["ready", "blocked", "analysing", "analysed"].includes(dataset.status) && dataset.report && (
          <Loaded dataset={dataset} saving={saving} onMapping={changeMapping} onKind={changeKind} onSheet={chooseSheet} />
        )}
      </div>

      {dataset && ["ready", "blocked", "analysing", "analysed"].includes(dataset.status) && dataset.report && (
        <footer className="footer-bar">
          <div>
            <div style={{ fontWeight: 500 }}>
              {dataset.report.blocking.length > 0 ? (
                "Fix the issue above before analyzing"
              ) : (
                <>
                  <span className="num">{dataset.report.rows_ready.toLocaleString("en-GB")}</span>{" "}
                  {dataset.kind === "catalogue" ? "items" : "tasks"} {dataset.status === "analysed" ? "analyzed" : "will be analyzed"}
                </>
              )}
            </div>
            <div className="muted" style={{ fontSize: 13 }}>
              {dataset.kind === "catalogue"
                ? dataset.status === "analysed" || dataset.status === "analysing"
                  ? "Changing a column choice clears the results; run the analysis again afterwards."
                  : "Nothing changes in your own systems. You review every result before you download."
                : "Finding duplicates works on product catalogues for now. If this file is one, choose Product catalogue above."}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link className="btn btn-ghost" href="/datasets">
              Back to datasets
            </Link>
            {dataset.status === "analysed" || dataset.status === "analysing" ? (
              <Link className="btn btn-primary" href={`/datasets/${id}/results`}>
                View results
              </Link>
            ) : (
              <button
                className="btn btn-primary"
                type="button"
                onClick={startAnalysis}
                disabled={saving || dataset.kind !== "catalogue" || dataset.report.blocking.length > 0}
              >
                Start analysis
              </button>
            )}
          </div>
        </footer>
      )}
    </>
  );
}

function Loaded({
  dataset,
  saving,
  onMapping,
  onKind,
  onSheet,
}: {
  dataset: Dataset;
  saving: boolean;
  onMapping: (column: string, field: string) => void;
  onKind: (kind: Kind) => void;
  onSheet: (sheet: string) => void;
}) {
  const report = dataset.report!;
  const fieldByColumn = Object.fromEntries(Object.entries(dataset.mapping).filter(([, c]) => c).map(([f, c]) => [c as string, f]));
  const usedColumns = report.columns.filter((c) => c.field).length;
  const warnings = report.warnings.filter((w) => w.severity === "warning").length;

  return (
    <>
      <div className="panel facts">
        <div>
          <span className="label">File</span>
          <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dataset.file.name}</span>
          <span className="label" style={{ fontWeight: 400 }}>
            {FORMAT_NAMES[dataset.file.format ?? ""] ?? "File"} · {formatBytes(dataset.file.size_bytes)}
          </span>
        </div>
        <div>
          {dataset.file.format === "xlsx" && dataset.file.sheets.length > 1 ? (
            <>
              <label className="label" htmlFor="sheet">
                Sheet
              </label>
              <select id="sheet" className="select" value={dataset.file.sheet ?? ""} onChange={(e) => onSheet(e.target.value)} disabled={!!dataset.file.raw_file_deleted_at}>
                {dataset.file.sheets.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name} ({s.approx_rows.toLocaleString("en-GB")} rows)
                  </option>
                ))}
              </select>
            </>
          ) : (
            <>
              <span className="label">{dataset.file.format === "xlsx" ? "Sheet" : "Columns"}</span>
              <span style={{ fontWeight: 500 }}>{dataset.file.format === "xlsx" ? dataset.file.sheet : dataset.columns.length}</span>
            </>
          )}
        </div>
        <div>
          <span className="label">{report.row_label === "item" ? "Items read" : "Rows read"}</span>
          <span className="fact-big num">{report.rows_read.toLocaleString("en-GB")}</span>
        </div>
        <div>
          <span className="label">Ready to analyze</span>
          <span className="fact-big num">{report.rows_ready.toLocaleString("en-GB")}</span>
        </div>
      </div>

      <KindChoice kind={dataset.kind} saving={saving} onKind={onKind} />

      <section className="panel">
        <div className="panel-head">
          <h2>Validation</h2>
          <div style={{ display: "flex", gap: 8 }}>
            {report.blocking.length === 0 ? <span className="badge badge-ok">No blocking errors</span> : <span className="badge badge-danger">{report.blocking.length} to fix</span>}
            {warnings > 0 && <span className="badge badge-warn">{warnings} {warnings === 1 ? "warning" : "warnings"}</span>}
          </div>
        </div>
        {report.blocking.map((b) => (
          <div className="issue" key={b.code} role="alert">
            <ErrorIcon />
            <div>
              <strong>{b.message}</strong>
              {(b.code === "no_title_column" || b.code === "no_name_column") && <span className="muted">Use the “Used as” menus below.</span>}
            </div>
            <span />
          </div>
        ))}
        {report.warnings.map((w) => (
          <Issue key={w.code} warning={w} datasetId={dataset.id} columns={dataset.columns} mapping={dataset.mapping} kind={dataset.kind} rowLabel={report.row_label} />
        ))}
        {report.blocking.length === 0 && report.warnings.length === 0 && (
          <div className="issue">
            <InfoIcon />
            <div>
              <strong>Everything looks good</strong>
            </div>
            <span />
          </div>
        )}
      </section>

      <section className="panel" aria-busy={saving}>
        <div className="panel-head">
          <h2>Columns</h2>
          <span className="label" style={{ fontWeight: 400 }}>
            {saving ? "Saving…" : `${report.columns.length} columns detected · ${usedColumns} used · every column kept in your export`}
          </span>
        </div>
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Column in your file</th>
                <th>Used as</th>
                <th>Sample value</th>
                <th className="right">Filled</th>
              </tr>
            </thead>
            <tbody>
              {report.columns.map((c) => (
                <tr key={c.name}>
                  <td className="mono">{c.name}</td>
                  <td>
                    <select className="select" aria-label={`${c.name} used as`} value={fieldByColumn[c.name] ?? ""} disabled={saving} onChange={(e) => onMapping(c.name, e.target.value)}>
                      <option value="">Not used</option>
                      {dataset.fields.map((f) => (
                        <option key={f.key} value={f.key}>
                          {f.label}
                          {f.required ? " (required)" : f.use === "display" ? " (display only)" : ""}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <span className="trunc muted">{c.sample || "—"}</span>
                  </td>
                  <td className="right num">{c.fill_percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <FirstRows dataset={dataset} />
    </>
  );
}

function Issue({
  warning,
  datasetId,
  columns,
  mapping,
  kind,
  rowLabel,
}: {
  warning: Warning;
  datasetId: string;
  columns: string[];
  mapping: Record<string, string | null>;
  kind: Kind;
  rowLabel: string;
}) {
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<RowsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!page) {
      try {
        setPage(await api<RowsPage>(`/v1/datasets/${datasetId}/rows?only=${encodeURIComponent(warning.code)}&limit=50`));
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "We couldn’t load those rows.");
      }
    }
  }

  const shown = previewColumns(columns, mapping, kind);
  const plural = rowLabel === "item" ? "items" : "rows";

  return (
    <div className="issue">
      {warning.severity === "warning" ? <WarnIcon /> : <InfoIcon />}
      <div>
        <strong>{warning.title}</strong>
        <span className="muted">{warning.detail}</span>
      </div>
      {warning.rows.length > 0 ? (
        <button className="btn btn-secondary btn-sm" type="button" onClick={toggle} aria-expanded={open}>
          {open ? "Hide" : `View ${warning.count.toLocaleString("en-GB")} ${warning.count === 1 ? rowLabel : plural}`}
        </button>
      ) : (
        <span />
      )}
      {open && (
        <div className="issue-rows">
          {error && <p style={{ padding: 12, color: "var(--danger)" }}>{error}</p>}
          {!error && !page && <p style={{ padding: 12 }} className="muted">Loading…</p>}
          {page && <RowsTable page={page} columns={shown} rowLabel={rowLabel} />}
          {page && page.total > page.rows.length && (
            <p className="label" style={{ padding: "8px 16px", fontWeight: 400 }}>
              Showing the first {page.rows.length} of {page.total.toLocaleString("en-GB")}. All are listed in your export.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function FirstRows({ dataset }: { dataset: Dataset }) {
  const api = useApi();
  const [page, setPage] = useState<RowsPage | null>(null);
  const sheet = dataset.file.sheet;

  useEffect(() => {
    let active = true;
    api<RowsPage>(`/v1/datasets/${dataset.id}/rows?limit=5`)
      .then((p) => active && setPage(p))
      .catch(() => active && setPage(null));
    return () => {
      active = false;
    };
  }, [api, dataset.id, sheet]);

  if (!page) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>First rows</h2>
        <span className="label" style={{ fontWeight: 400 }}>
          {page.total.toLocaleString("en-GB")} in total
        </span>
      </div>
      <RowsTable page={page} columns={previewColumns(dataset.columns, dataset.mapping, dataset.kind)} rowLabel={dataset.report?.row_label ?? "row"} />
    </section>
  );
}

function KindChoice({ kind, saving, onKind }: { kind: Kind; saving: boolean; onKind: (kind: Kind) => void }) {
  const options: { value: Kind; label: string; hint: string }[] = [
    { value: "catalogue", label: "Product catalogue", hint: "Parts or products, one per row. Finds duplicate lines." },
    { value: "tasks", label: "Task export", hint: "Tasks or tickets, one per row. Finds duplicate work." },
  ];
  return (
    <section className="panel kind-choice" aria-busy={saving}>
      <div>
        <h2 id="kind-title">What kind of file is this?</h2>
        <p className="muted">Atlas guessed from the column names. Changing it matches the columns again.</p>
      </div>
      <div className="kind-options" role="radiogroup" aria-labelledby="kind-title">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={kind === o.value}
            className="kind-option"
            disabled={saving}
            onClick={() => onKind(o.value)}
          >
            <strong>{o.label}</strong>
            <span className="muted">{o.hint}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function previewColumns(columns: string[], mapping: Record<string, string | null>, kind: Kind): string[] {
  const mapped = PREVIEW_FIELDS[kind].map((f) => mapping[f]).filter((c): c is string => !!c);
  return mapped.length >= 2 ? mapped : columns.slice(0, 5);
}

function RowsTable({ page, columns, rowLabel }: { page: RowsPage; columns: string[]; rowLabel: string }) {
  return (
    <div className="table-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th>{rowLabel === "item" ? "Item" : "Row"}</th>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.rows.map((r) => (
            <tr key={r.row_number}>
              <td className="mono num muted">{r.row_number}</td>
              {r.malformed ? (
                <td colSpan={columns.length} className="muted">
                  Couldn’t be read
                </td>
              ) : (
                columns.map((c) => (
                  <td key={c}>
                    <span className="trunc">{r.values[c] || <span className="muted">—</span>}</span>
                  </td>
                ))
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
