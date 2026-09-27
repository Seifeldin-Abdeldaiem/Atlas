import { SignedIn, SignedOut } from "@clerk/nextjs";
import Link from "next/link";

import Aha from "@/components/landing/Aha";
import Demo from "@/components/landing/Demo";
import SmoothScroll from "@/components/landing/SmoothScroll";
import { Logo } from "@/components/ui";

// Public landing page. Everything here is static: no API calls, no uploads.
// The example rows and Atlas's answers live in components/landing/sample.ts.
//
// Written to pass a five-second test: the first heading says what Atlas does
// in plain words, in the display font (used only for that sentence and the
// closing one), and the example beside it plays out in under four seconds.
// Headings alone tell the whole story, for people who only skim.

const SIGN_UP = "/sign-up";
const SOURCE = "https://github.com/Seifeldin-Abdeldaiem/Atlas";

function Start({ className = "btn btn-primary" }: { className?: string }) {
  return (
    <>
      <SignedOut>
        <Link href={SIGN_UP} className={className}>
          Try it free
        </Link>
      </SignedOut>
      <SignedIn>
        <Link href="/datasets" className={className}>
          Open Atlas
        </Link>
      </SignedIn>
    </>
  );
}

function Check() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2.5 7.5l3 3 6-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Home() {
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
          <a href="#faq">Questions</a>
        </nav>
        <div className="lp-nav-actions">
          <SignedOut>
            <Link href="/sign-in" className="btn btn-ghost btn-sm">
              Sign in
            </Link>
          </SignedOut>
          <Start className="btn btn-primary btn-sm" />
        </div>
      </header>

      <main>
        <section className="lp-hero lp-wrap">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">For shops, parts stores and wholesalers</p>
            <h1 className="display lp-explain">
              Atlas finds the same product <span className="lp-mark">listed more than once</span> in your spreadsheet.
            </h1>
            <p className="lp-lead">
              Different spellings split one product across several rows, each with its own stock count. Atlas puts them
              back together, so you can see what you really have.
            </p>
            <div className="lp-cta">
              <Start />
              <a href="#how" className="btn btn-secondary">
                See how it works
              </a>
            </div>
            <ul className="lp-assure">
              <li>
                <Check /> Free to try, no card needed
              </li>
              <li>
                <Check /> Works with Excel and CSV
              </li>
              <li>
                <Check /> You check every match
              </li>
            </ul>
          </div>
          <Aha />
        </section>

        <section className="lp-band" aria-labelledby="cost-title">
          <div className="lp-wrap">
            <h2 id="cost-title" className="serif lp-band-title">
              One product on several rows quietly costs you money
            </h2>
            <div className="lp-costs">
              <div>
                <span className="lp-num serif">01</span>
                <h3>You buy what you already have</h3>
                <p>One row says you are running low, so you reorder. The same product is on the shelf under another name.</p>
              </div>
              <div>
                <span className="lp-num serif">02</span>
                <h3>No stock count is right</h3>
                <p>The stock is split across rows, so none of them shows how many you really hold.</p>
              </div>
              <div>
                <span className="lp-num serif">03</span>
                <h3>People pick the wrong row</h3>
                <p>Staff and customers see several versions of one item and have to guess which one is right.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="how" className="lp-section lp-wrap" aria-labelledby="how-title">
          <div className="lp-section-head">
            <h2 id="how-title" className="serif">
              How it works
            </h2>
            <p className="lp-lead">Three steps. Nothing to install and nothing to connect.</p>
          </div>
          <ol className="lp-steps">
            <li>
              <div className="lp-step-art" aria-hidden="true">
                <div className="lp-art-file">
                  <span className="lp-art-icon">XLSX</span>
                  <div>
                    <strong>stock-list.xlsx</strong>
                    <span>1,240 rows</span>
                  </div>
                </div>
                <div className="lp-art-cols">
                  <span>Name</span>
                  <span>Code</span>
                  <span>Brand</span>
                  <span>Stock</span>
                </div>
              </div>
              <span className="lp-step-n">1</span>
              <h3>Upload your spreadsheet</h3>
              <p>
                Export your product list from your stock system, online shop or Excel. Atlas finds the name, code, brand
                and stock columns for you.
              </p>
            </li>
            <li>
              <div className="lp-step-art" aria-hidden="true">
                <div className="lp-art-group">
                  <div className="lp-art-group-head">
                    <strong>Bearing, SKF 6205-2RS</strong>
                    <span className="badge badge-ok">High</span>
                  </div>
                  <span className="lp-art-reason">Same brand, same part number and variant</span>
                  <div className="lp-art-actions">
                    <span className="lp-art-btn lp-art-btn-primary">Confirm group</span>
                    <span className="lp-art-btn">Not duplicates</span>
                  </div>
                </div>
              </div>
              <span className="lp-step-n">2</span>
              <h3>Check what Atlas found</h3>
              <p>
                Each group shows the rows and the reason they match. Confirm it, or mark it as not duplicates. Nothing
                changes without you.
              </p>
            </li>
            <li>
              <div className="lp-step-art" aria-hidden="true">
                <div className="lp-art-sheet">
                  <div className="lp-art-row lp-art-row-head">
                    <span>name</span>
                    <span className="lp-art-added">atlas_group</span>
                    <span className="lp-art-added">atlas_role</span>
                  </div>
                  <div className="lp-art-row">
                    <span>6205 2RS SKF bearing</span>
                    <span className="lp-art-added">G-0001</span>
                    <span className="lp-art-added">master</span>
                  </div>
                  <div className="lp-art-row">
                    <span>Bearing 6205-2RS (SKF)</span>
                    <span className="lp-art-added">G-0001</span>
                    <span className="lp-art-added">duplicate</span>
                  </div>
                </div>
              </div>
              <span className="lp-step-n">3</span>
              <h3>Download a clean file</h3>
              <p>
                You get your own file back with every row kept and the answers added in new columns, ready for Excel or
                your system.
              </p>
            </li>
          </ol>
        </section>

        <section id="careful" className="lp-section lp-wrap" aria-labelledby="careful-title">
          <div className="lp-section-head">
            <h2 id="careful-title" className="serif">
              Similar isn&apos;t the same. Atlas knows the difference.
            </h2>
            <p className="lp-lead">
              Matching words is easy. The hard part is spotting two products that only look alike, because merging
              those by mistake costs more than missing a duplicate.
            </p>
          </div>
          <div className="lp-care">
            <article>
              <h3>It checks the details</h3>
              <p>Brand, part number, size, thread, material, colour and type. One real difference keeps two rows apart.</p>
              <div className="lp-care-ex">
                <span>Hex bolt M8x25</span>
                <span className="lp-care-neq" aria-label="is not the same as">
                  ≠
                </span>
                <span>Hex bolt M8x20</span>
              </div>
            </article>
            <article>
              <h3>It tells you why</h3>
              <p>Every match comes with a plain reason, so you can check it in seconds instead of taking it on trust.</p>
              <p className="lp-care-quote">&ldquo;Same brand (SKF), same part number and variant (6205-2RS).&rdquo;</p>
            </article>
            <article>
              <h3>It asks when it isn&apos;t sure</h3>
              <p>If two names don&apos;t clearly describe the same product, Atlas lists them under Needs review instead of guessing.</p>
              <div className="lp-care-ex lp-care-ex-stack">
                <span>Loctite 243 threadlocker 50ml</span>
                <span className="lp-care-q">?</span>
                <span>Threadlock medium strength blue 243 50 ml</span>
              </div>
            </article>
            <article>
              <h3>It reads messy lists</h3>
              <p>Mixed-up word order, missing brands, stray symbols, and names written in Arabic, even on the same list.</p>
              <div className="lp-chips">
                <span>6205-2RS</span>
                <span>6205 2RS</span>
                <span>2RS 6205</span>
                <span lang="ar" dir="rtl">
                  رولمان بلي
                </span>
              </div>
            </article>
          </div>
          <dl className="lp-proof">
            <div>
              <dt className="serif num">0</dt>
              <dd>wrong matches in our tests</dd>
            </div>
            <div>
              <dt className="serif num">95.3%</dt>
              <dd>of duplicates found on a test list it had never seen</dd>
            </div>
            <div>
              <dt className="serif num">20,000</dt>
              <dd>rows checked in about 20 seconds</dd>
            </div>
            <div>
              <dt className="serif num">7 days</dt>
              <dd>then your uploaded files are deleted</dd>
            </div>
          </dl>
          <p className="lp-small muted">
            Measured on four labelled test lists, one of them never used for tuning, with Atlas&apos;s rules alone. Your
            own list may score differently. Anything Atlas can&apos;t decide is left for you.
          </p>
        </section>

        <section id="example" className="lp-section lp-wrap" aria-labelledby="example-title">
          <div className="lp-section-head">
            <h2 id="example-title" className="serif">
              Try the full example
            </h2>
            <p className="lp-lead">
              A small made-up list of bearings, bolts and glue, with Atlas&apos;s real results. Click through the tabs.
            </p>
          </div>
          <Demo />
        </section>

        <section id="trust" className="lp-section lp-wrap" aria-labelledby="trust-title">
          <div className="lp-section-head">
            <h2 id="trust-title" className="serif">
              Your data stays yours
            </h2>
            <p className="lp-lead">Your product list is business information. Atlas treats it that way.</p>
          </div>
          <div className="lp-trust">
            <div>
              <h3>Walled off</h3>
              <p>Each business&apos;s data is kept apart by the database itself, not only by the app.</p>
            </div>
            <div>
              <h3>Deleted after 7 days</h3>
              <p>Uploaded files are removed automatically after a week, or sooner with one click.</p>
            </div>
            <div>
              <h3>Your systems stay untouched</h3>
              <p>Atlas never connects to your stock system. It only reads the file you upload.</p>
            </div>
            <div>
              <h3>Files handled safely</h3>
              <p>Macros and formulas in your files are never run. Files stay private, never public links.</p>
            </div>
          </div>
        </section>

        <section id="faq" className="lp-section lp-wrap" aria-labelledby="faq-title">
          <div className="lp-section-head">
            <h2 id="faq-title" className="serif">
              Common questions
            </h2>
          </div>
          <div className="lp-faq">
            <details>
              <summary>What counts as a duplicate?</summary>
              <p>
                Two or more rows that are really the same product, written differently, like &ldquo;SKF 6205-2RS
                bearing&rdquo; and &ldquo;Bearing 6205 2RS (SKF)&rdquo;. Products that only look alike, like a 25 mm and a
                20 mm bolt, are kept apart.
              </p>
            </details>
            <details>
              <summary>What file do I need?</summary>
              <p>
                Your product list as an Excel (.xlsx), CSV or JSON file, with one product per row. Most stock systems and
                online shops can export one. Atlas finds the right columns itself, and you can change them.
              </p>
            </details>
            <details>
              <summary>Will it change my stock system?</summary>
              <p>No. Atlas never connects to your systems. You download a file with the results and decide what to change.</p>
            </details>
            <details>
              <summary>What if Atlas gets one wrong?</summary>
              <p>
                You check every group before you download. Mark a group as not duplicates and Atlas remembers your answer
                the next time you run it.
              </p>
            </details>
            <details>
              <summary>What does it cost?</summary>
              <p>Nothing. Atlas is free to try while it is new, and there is no card to enter.</p>
            </details>
          </div>
        </section>

        <section className="lp-wrap">
          <div className="lp-final">
            <div>
              <h2 className="display">See the duplicates in your own spreadsheet.</h2>
              <p>Upload a file, check what Atlas finds, download a clean copy. Free to try, no card needed.</p>
            </div>
            <Start className="btn lp-btn-light" />
          </div>
        </section>
      </main>

      <footer className="lp-footer lp-wrap">
        <div className="brand">
          <Logo size={18} />
          <span className="serif">Atlas</span>
        </div>
        <span className="muted">© 2026 Atlas</span>
        <a href={SOURCE}>Source code</a>
        <Link href="/sign-in">Sign in</Link>
      </footer>
    </div>
  );
}
