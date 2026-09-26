"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { EmptyGlyph, StatusBadge } from "@/components/ui";
import { ApiError, useApi, type DatasetSummary } from "@/lib/api";

const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export default function DatasetsPage() {
  const api = useApi();
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api<{ datasets: DatasetSummary[] }>("/v1/datasets")
      .then((body) => active && setDatasets(body.datasets))
      .catch((e: unknown) => active && setError(e instanceof ApiError ? e.message : "We couldn't load your datasets."));
    return () => {
      active = false;
    };
  }, [api]);

  return (
    <>
      <header className="topbar">
        <span>Datasets</span>
        {datasets && datasets.length > 0 && (
          <Link className="btn btn-primary btn-sm" href="/datasets/new">
            Upload a file
          </Link>
        )}
      </header>
      <div className="page">
        <div className="page-title">
          <div>
            <h1 className="serif">Datasets</h1>
            <p>Each upload is a dataset. Open one to check its data or review its findings.</p>
          </div>
        </div>

        {error && (
          <div className="panel state" role="alert">
            <h2>We couldn’t load your datasets</h2>
            <p>{error}</p>
            <button className="btn btn-secondary" type="button" onClick={() => window.location.reload()}>
              Try again
            </button>
          </div>
        )}

        {!error && datasets === null && (
          <div className="panel state" aria-busy="true">
            <p>Loading datasets…</p>
          </div>
        )}

        {datasets && datasets.length === 0 && (
          <div className="panel state">
            <EmptyGlyph />
            <h2>No datasets yet</h2>
            <p>Upload a product catalogue or task export to find the duplicates in it.</p>
            <Link className="btn btn-primary" href="/datasets/new">
              Upload a file
            </Link>
          </div>
        )}

        {datasets && datasets.length > 0 && (
          <section className="panel">
            <div className="table-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Status</th>
                    <th className="right">Ready to analyze</th>
                    <th>Uploaded</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link href={`/datasets/${d.id}/${d.status === "analysed" || d.status === "analysing" ? "results" : "preview"}`} style={{ fontWeight: 500 }}>
                          {d.name}
                        </Link>
                        <div className="label" style={{ fontWeight: 400 }}>
                          {d.kind === "catalogue" ? "Product catalogue" : "Task export"}
                          {d.file_name ? ` · ${d.file_name}` : ""}
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={d.status} />
                      </td>
                      <td className="right num">{d.rows_ready?.toLocaleString("en-GB") ?? "—"}</td>
                      <td className="num muted">{dateFormat.format(new Date(d.created_at))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </>
  );
}
