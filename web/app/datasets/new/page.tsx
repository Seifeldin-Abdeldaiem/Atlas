"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";

import { Crumbs, FileErrorGlyph, Sep, Steps, UploadGlyph } from "@/components/ui";
import { ApiError, formatBytes, uploadFile } from "@/lib/api";

const MAX_MB = 25;
const ACCEPT = ".csv,.tsv,.txt,.xlsx,.json";

type State =
  | { kind: "idle" }
  | { kind: "uploading"; file: File; progress: number }
  | { kind: "error"; message: string; fileName?: string };

export default function UploadPage() {
  const { getToken } = useAuth();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);

  async function start(file: File) {
    if (file.size === 0) {
      setState({ kind: "error", fileName: file.name, message: "This file is empty. Export it again and upload the new file." });
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setState({
        kind: "error",
        fileName: file.name,
        message: `This file is ${formatBytes(file.size)}, larger than ${MAX_MB} MB. Split it into smaller files or remove columns you don’t need.`,
      });
      return;
    }
    setState({ kind: "uploading", file, progress: 0 });
    try {
      const token = await getToken();
      const { id } = await uploadFile(token, file, (progress) => setState({ kind: "uploading", file, progress }));
      router.push(`/datasets/${id}/preview`);
    } catch (e) {
      setState({ kind: "error", fileName: file.name, message: e instanceof ApiError ? e.message : "The upload didn’t go through. Try again." });
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file && state.kind !== "uploading") void start(file);
  }

  const choose = () => input.current?.click();

  return (
    <>
      <header className="topbar">
        <Crumbs>
          <Link href="/datasets">Datasets</Link>
          <Sep />
          <span className="here">New analysis</span>
        </Crumbs>
      </header>

      <div className="page">
        <div className="page-title">
          <div>
            <h1 className="serif">Upload your file</h1>
            <p>Atlas reads the file, shows you exactly what it found, and waits for your go-ahead before analyzing anything.</p>
          </div>
          <Steps current={1} />
        </div>

        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          className="visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void start(file);
          }}
        />

        <div
          className="dropzone"
          data-dragging={dragging}
          onDragOver={(e) => {
            e.preventDefault();
            if (state.kind !== "uploading") setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          aria-live="polite"
        >
          {state.kind === "idle" && (
            <>
              <UploadGlyph />
              <div>
                <div style={{ fontSize: 17, lineHeight: "24px", fontWeight: 500 }}>Drag your file here</div>
                <div className="muted">CSV, XLSX or JSON · up to {MAX_MB} MB and 20,000 rows</div>
              </div>
              <button className="btn btn-secondary" type="button" onClick={choose}>
                Choose a file
              </button>
            </>
          )}

          {state.kind === "uploading" && (
            <>
              <div style={{ fontWeight: 500 }}>Uploading {state.file.name}</div>
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(state.progress * 100)} aria-label="Upload progress">
                <div style={{ width: `${Math.round(state.progress * 100)}%` }} />
              </div>
              <div className="label num" style={{ fontWeight: 400 }}>
                {formatBytes(state.file.size * state.progress)} of {formatBytes(state.file.size)}
              </div>
            </>
          )}

          {state.kind === "error" && (
            <div role="alert" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
              <FileErrorGlyph />
              <div>
                <h2 style={{ fontSize: 17, lineHeight: "24px", fontWeight: 600 }}>We can’t use this file</h2>
                <p className="muted" style={{ maxWidth: 440, marginTop: 6 }}>
                  {state.fileName ? <strong style={{ fontWeight: 500, color: "var(--ink)" }}>{state.fileName}: </strong> : null}
                  {state.message}
                </p>
              </div>
              <button className="btn btn-primary" type="button" onClick={choose}>
                Choose another file
              </button>
            </div>
          )}
        </div>

        <div className="explainers">
          <section>
            <h2>What can I upload?</h2>
            <ul>
              <li>A product catalogue or a task export, as CSV, XLSX or JSON, with one item per row.</li>
              <li>Only a name or title column is required. Part numbers and brands make catalogue results much better.</li>
              <li>Every other column is kept and returned in your export.</li>
            </ul>
          </section>
          <section>
            <h2>How is my data used?</h2>
            <ul>
              <li>Stored encrypted and visible only to people in your workspace.</li>
              <li>Some text may be sent to our AI providers for analysis, under terms that prohibit training on it.</li>
              <li>The uploaded file is deleted after 7 days. You can delete the whole dataset whenever you like.</li>
            </ul>
          </section>
          <section>
            <h2>What will the analysis find?</h2>
            <ul>
              <li>Exact and likely duplicates, gathered into groups with a suggested line to keep.</li>
              <li>Look-alikes that are actually different, such as a 2RS and a ZZ bearing.</li>
              <li>A specific reason for every finding. Nothing changes in your own systems.</li>
            </ul>
          </section>
        </div>
      </div>
    </>
  );
}
