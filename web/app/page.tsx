import { SignedIn, SignedOut } from "@clerk/nextjs";
import Link from "next/link";

import Demo from "@/components/landing/Demo";
import SmoothScroll from "@/components/landing/SmoothScroll";
import { groups, groupStock } from "@/components/landing/sample";
import { Logo } from "@/components/ui";

// Public landing page. Everything here is static: no API calls, no uploads.
// The demo uses the hand-made example in components/landing/sample.ts.

const PILOT_HREF = "/sign-up";

export default function Home() {
  const bearing = groups[0];

  return (
    <div className="lp">
      <SmoothScroll />
      <header className="lp-nav">
        <Link href="/" className="brand" aria-label="Atlas home">
          <Logo />
          <span className="serif">Atlas</span>
        </Link>
        <nav className="lp-links" aria-label="Page sections">
          <a href="#how">How it works</a>
          <a href="#example">Example</a>
          <a href="#trust">Your data</a>
        </nav>
        <div className="lp-nav-actions">
          <SignedOut>
            <Link href="/sign-in" className="btn btn-ghost btn-sm">
              Sign in
            </Link>
            <Link href={PILOT_HREF} className="btn btn-primary btn-sm">
              Join the pilot
            </Link>
          </SignedOut>
          <SignedIn>
            <Link href="/datasets" className="btn btn-primary btn-sm">
              Open Atlas
            </Link>
          </SignedIn>
        </div>
      </header>

      <main>
        <section className="lp-hero lp-wrap">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">For parts stores, distributors and online shops</p>
            <h1 className="serif">The same part, listed three times.</h1>
            <p className="lp-lead">
              Duplicate lines split your stock count, so you reorder parts that are already on the shelf. Upload a
              spreadsheet of your catalogue and Atlas shows you which lines are the same item.
            </p>
            <div className="lp-cta">
              <Link href={PILOT_HREF} className="btn btn-primary">
                Join the free pilot
              </Link>
              <a href="#example" className="btn btn-secondary">
                See an example
              </a>
            </div>
            <p className="lp-small muted">Works with CSV, Excel and JSON exports. Nothing to install or connect.</p>
          </div>

          <figure className="lp-hero-card" aria-label="Example: three catalogue lines that are the same bearing">
            <div className="lp-card-head">
              <span className="label">Your catalogue</span>
              <span className="label num">Stock</span>
            </div>
            <ul className="lp-lines">
              {bearing.rows.map((r) => (
                <li key={r.code}>
                  <span className="mono muted">{r.code}</span>
                  <span className="lp-line-name">{r.name}</span>
                  <span className="num">{r.stock}</span>
                </li>
              ))}
            </ul>
            <div className="lp-verdict">
              <span className="lp-verdict-mark" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2.5 7.5l3 3 6-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <div>
                <strong>One item: {bearing.standardName.replace("Bearing, Deep Groove, ", "")}</strong>
                <span>
                  You have <b className="num">{groupStock(bearing)}</b> in stock, not {bearing.rows[0].stock}.
                </span>
              </div>
            </div>
            <div className="lp-verdict lp-verdict-warn">
              <span className="lp-verdict-mark" aria-hidden="true">≠</span>
              <div>
                <strong>SKF 6205-ZZ is kept separate</strong>
                <span>Metal shields, not rubber seals. A different part.</span>
              </div>
            </div>
            <figcaption className="lp-small muted">Example data</figcaption>
          </figure>
        </section>

        <section className="lp-band" aria-labelledby="cost-title">
          <div className="lp-wrap">
            <h2 id="cost-title" className="visually-hidden">
              What duplicate lines cost
            </h2>
            <div className="lp-costs">
              <div>
                <span className="lp-num serif">01</span>
                <h3>Stock gets split</h3>
                <p>Each copy of a part keeps its own count. None of them shows what you really have.</p>
              </div>
              <div>
                <span className="lp-num serif">02</span>
                <h3>You buy what you already have</h3>
                <p>One line reads low, so it gets reordered while the same part sits under another code.</p>
              </div>
              <div>
                <span className="lp-num serif">03</span>
                <h3>People pick the wrong line</h3>
                <p>Staff and customers find three versions of one item and have to guess which is right.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="how" className="lp-section lp-wrap" aria-labelledby="how-title">
          <div className="lp-section-head">
            <h2 id="how-title" className="serif">
              How it works
            </h2>
            <p className="lp-lead">Three steps. You stay in control, and nothing changes until you say so.</p>
          </div>
          <ol className="lp-steps">
            <li>
              <span className="lp-step-n">1</span>
              <h3>Upload your export</h3>
              <p>
                Export your product list from your stock system, shop or spreadsheet. Atlas works out which column is
                the name, part number, brand, stock and cost.
              </p>
            </li>
            <li>
              <span className="lp-step-n">2</span>
              <h3>Review the matches</h3>
              <p>
                See each group of duplicates with the reason Atlas matched them. Parts that only look alike are listed
                separately. Approve or reject each group.
              </p>
            </li>
            <li>
              <span className="lp-step-n">3</span>
              <h3>Download a clean file</h3>
              <p>
                Get your file back with the duplicates marked and a suggested line to keep. Filter it in Excel or
                import it into your system.
              </p>
            </li>
          </ol>
        </section>

        <section id="example" className="lp-section lp-wrap" aria-labelledby="example-title">
          <div className="lp-section-head">
            <h2 id="example-title" className="serif">
              See what you would get
            </h2>
            <p className="lp-lead">
              A sample catalogue with bearings, fasteners and adhesives. Click through the four views.
            </p>
          </div>
          <Demo />
          <p className="lp-small muted lp-disclaimer">
            Example data made up to show the layout. Your results will depend on your catalogue.
          </p>
        </section>

        <section id="trust" className="lp-section lp-wrap" aria-labelledby="trust-title">
          <div className="lp-section-head">
            <h2 id="trust-title" className="serif">
              Your data stays yours
            </h2>
            <p className="lp-lead">Your catalogue is commercial information. We treat it that way.</p>
          </div>
          <div className="lp-trust">
            <div>
              <h3>Kept separate</h3>
              <p>Each business&apos;s data is walled off inside the database itself, not only in the app.</p>
            </div>
            <div>
              <h3>Deleted after 7 days</h3>
              <p>Uploaded files are removed automatically after a week. Delete them sooner with one click.</p>
            </div>
            <div>
              <h3>Nothing changes without you</h3>
              <p>Atlas suggests. You approve. Your stock system is never touched.</p>
            </div>
            <div>
              <h3>Files handled safely</h3>
              <p>Macros and formulas in uploaded files are never run. Files are private, never public links.</p>
            </div>
          </div>
        </section>

        <section className="lp-wrap">
          <div className="lp-pilot">
            <div>
              <h2 className="serif">Try it free on your own catalogue</h2>
              <p>
                We are working with a small group of businesses before launch. You get a checked, cleaned catalogue at
                no cost. We ask for honest feedback.
              </p>
            </div>
            <Link href={PILOT_HREF} className="btn lp-btn-light">
              Join the pilot
            </Link>
          </div>
        </section>
      </main>

      <footer className="lp-footer lp-wrap">
        <div className="brand">
          <Logo size={18} />
          <span className="serif">Atlas</span>
        </div>
        <span className="muted">© 2026 Atlas</span>
        <Link href="/sign-in">Sign in</Link>
      </footer>
    </div>
  );
}
