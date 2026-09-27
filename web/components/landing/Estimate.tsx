"use client";

import { useId, useState, type ReactNode } from "react";

// A rough estimate from the visitor's own numbers: the stock value sitting on
// duplicate rows, which is what Atlas measures in a real file ("value on
// duplicate lines"). Duplicate rows are assumed to hold an average share of
// the stock, so the value is simply total stock value x the duplicate share.
// The default share is cautious on purpose: industry reports on parts lists
// often find 10 to 20%, and an estimate that oversells would cost trust.

const DEFAULTS = { products: 5000, value: 200000, share: 5 };

const toNumber = (text: string) => {
  const n = Number(text.replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) ? n : 0;
};
const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const pounds = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });

export default function Estimate({ cta }: { cta: ReactNode }) {
  const id = useId();
  const [products, setProducts] = useState(whole.format(DEFAULTS.products));
  const [value, setValue] = useState(whole.format(DEFAULTS.value));
  const [share, setShare] = useState(DEFAULTS.share);

  const rows = Math.round((toNumber(products) * share) / 100);
  const atRisk = (toNumber(value) * share) / 100;
  const tidy = (text: string) => (text.trim() ? whole.format(toNumber(text)) : "");

  return (
    <div className="lp-calc">
      <div className="lp-calc-inputs">
        <h3>What could it be costing you?</h3>
        <label className="lp-field" htmlFor={`${id}-products`}>
          Products in your list
          <input
            id={`${id}-products`}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={products}
            onChange={(e) => setProducts(e.target.value)}
            onBlur={(e) => setProducts(tidy(e.target.value))}
          />
        </label>
        <label className="lp-field" htmlFor={`${id}-value`}>
          Total value of your stock
          <span className="lp-money-input">
            <span aria-hidden="true">£</span>
            <input
              id={`${id}-value`}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onBlur={(e) => setValue(tidy(e.target.value))}
            />
          </span>
        </label>
        <label className="lp-field" htmlFor={`${id}-share`}>
          <span className="lp-field-row">
            Rows that are duplicates{" "}
            <output htmlFor={`${id}-share`} className="num">
              {share}%
            </output>
          </span>
          <input
            id={`${id}-share`}
            type="range"
            min={1}
            max={20}
            step={1}
            value={share}
            aria-valuetext={`${share} percent`}
            onChange={(e) => setShare(Number(e.target.value))}
          />
        </label>
        <p className="lp-calc-note">
          We start at a cautious 5%. Industry reports on parts lists often find 10 to 20%.
        </p>
      </div>

      <div className="lp-calc-result" aria-live="polite">
        <span className="lp-calc-big serif num">{pounds.format(atRisk)}</span>
        <p>
          of stock could be sitting on about {whole.format(rows)} duplicate {rows === 1 ? "row" : "rows"}, where it is easy
          to miss and buy again.
        </p>
        <p className="lp-calc-sum num">
          {pounds.format(toNumber(value))} × {share}% = {pounds.format(atRisk)}
        </p>
        <p className="lp-calc-next">A rough guess. Upload your list to get the real figure.</p>
        {cta}
      </div>
    </div>
  );
}
