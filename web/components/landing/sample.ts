// A small made-up stock list for the public landing page, and what Atlas's
// matcher really says about it: the groups, reasons, look-alikes and the pair
// it isn't sure about are copied from its output. backend/tests/test_matching.py
// (test_landing_example) checks the matcher still gives these answers, so keep
// the rows in step with that test.

export type SampleRow = {
  code: string;
  name: string;
  brand: string;
  stock: number;
  cost: number;
};

export type SampleGroup = {
  id: string;
  standardName: string;
  confidence: "High" | "Medium";
  reason: string;
  masterCode: string;
  rows: SampleRow[];
};

export type SamplePair = {
  a: SampleRow;
  b: SampleRow;
  difference: string;
  detail: string;
};

const r = (code: string, name: string, brand: string, stock: number, cost: number): SampleRow => ({ code, name, brand, stock, cost });

const BRG_0142 = r("BRG-0142", "SKF 6205-2RS Deep Groove Ball Bearing", "SKF", 12, 4.2);
const BRG_0388 = r("BRG-0388", "6205 2RS SKF bearing", "SKF", 18, 4.35);
const BRG_1177 = r("BRG-1177", "Bearing 6205-2RS (SKF)", "", 12, 3.95);
const BRG_2051 = r("BRG-2051", "رولمان بلي 6205 2RS اس كي اف", "", 6, 4.1);
const BRG_0143 = r("BRG-0143", "SKF 6205-ZZ Deep Groove Ball Bearing", "SKF", 10, 3.8);
const BRG_0412 = r("BRG-0412", "SKF 6205-2RS/C3", "SKF", 4, 5.1);
const FST_2210 = r("FST-2210", "Hex bolt M8x25 A2 SS", "", 400, 0.18);
const FST_3019 = r("FST-3019", "M8 X 25MM HEX HD BOLT STAINLESS", "", 250, 0.21);
const FST_2208 = r("FST-2208", "Hex bolt M8x20 A2 SS", "", 300, 0.16);
const CHM_0071 = r("CHM-0071", "Loctite 243 threadlocker 50ml", "Loctite", 9, 12.1);
const CHM_0460 = r("CHM-0460", "Threadlock medium strength blue 243 50 ml", "", 6, 11.4);

export const allRows = [BRG_0142, BRG_0388, BRG_1177, BRG_2051, BRG_0143, BRG_0412, FST_2210, FST_3019, FST_2208, CHM_0071, CHM_0460];

export const groups: SampleGroup[] = [
  {
    id: "G-0001",
    standardName: "Bearing, SKF 6205-2RS",
    confidence: "High",
    reason: "Same brand (SKF), same part number and variant (6205-2RS).",
    masterCode: "BRG-0388",
    rows: [BRG_0142, BRG_0388, BRG_1177, BRG_2051],
  },
  {
    id: "G-0002",
    standardName: "Bolt, Hex, M8 x 25 mm, A2 Stainless",
    confidence: "Medium",
    reason: "Same kind of product (bolt) with the same thread and length. No part number to confirm.",
    masterCode: "FST-2210",
    rows: [FST_2210, FST_3019],
  },
];

export const lookalikes: SamplePair[] = [
  {
    a: BRG_0142,
    b: BRG_0143,
    difference: "Seal type",
    detail: "Different seal type: 2RS has rubber seals on both sides, ZZ has metal shields on both sides.",
  },
  { a: BRG_0388, b: BRG_0412, difference: "Clearance", detail: "Only one has C3 (larger) internal clearance (C3)." },
  { a: BRG_0143, b: BRG_0412, difference: "Clearance", detail: "Only one has C3 (larger) internal clearance (C3)." },
  { a: FST_2210, b: FST_2208, difference: "Length", detail: "Different lengths: 25 mm and 20 mm." },
];

export const unsure: SamplePair[] = [
  {
    a: CHM_0071,
    b: CHM_0460,
    difference: "Not sure",
    detail: "Same part number (243), but the names don't clearly describe the same product.",
  },
];

// The hero animation: one product typed four ways, and a look-alike between them.
export const heroRows = [
  { n: 1, row: BRG_0142, same: true },
  { n: 2, row: BRG_0143, same: false },
  { n: 3, row: BRG_0388, same: true },
  { n: 4, row: BRG_2051, same: true },
  { n: 5, row: BRG_1177, same: true },
];

export function groupStock(g: SampleGroup) {
  return g.rows.reduce((sum, row) => sum + row.stock, 0);
}

export function duplicateRows(g: SampleGroup) {
  return g.rows.filter((row) => row.code !== g.masterCode);
}

export function duplicateValue(g: SampleGroup) {
  return duplicateRows(g).reduce((sum, row) => sum + row.stock * row.cost, 0);
}

export const totals = {
  rows: allRows.length,
  groups: groups.length,
  duplicateLines: groups.reduce((n, g) => n + duplicateRows(g).length, 0),
  unitsOnDuplicates: groups.reduce((n, g) => n + duplicateRows(g).reduce((s, row) => s + row.stock, 0), 0),
  valueOnDuplicates: groups.reduce((n, g) => n + duplicateValue(g), 0),
};

export const money = (n: number) =>
  n.toLocaleString("en-GB", { style: "currency", currency: "GBP", minimumFractionDigits: 2 });
