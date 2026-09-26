// Hand-made example for the public landing page. It is not produced by Atlas's
// matching (not built yet) and is labelled "Example results" wherever shown.
// Replace with real output on the bearings test file once matching exists.

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

export type SampleLookalike = {
  a: SampleRow;
  b: SampleRow;
  difference: string;
  detail: string;
};

export const groups: SampleGroup[] = [
  {
    id: "G-0001",
    standardName: "Bearing, Deep Groove, SKF 6205-2RS",
    confidence: "High",
    reason: "Same brand, same part number (6205) and same seal type (2RS). Only the wording differs.",
    masterCode: "BRG-0388",
    rows: [
      { code: "BRG-0142", name: "SKF 6205-2RS Deep Groove Ball Bearing", brand: "SKF", stock: 12, cost: 4.2 },
      { code: "BRG-0388", name: "6205 2RS SKF bearing", brand: "SKF", stock: 18, cost: 4.35 },
      { code: "BRG-1177", name: "Bearing 6205-2RS (SKF)", brand: "", stock: 12, cost: 3.95 },
    ],
  },
  {
    id: "G-0002",
    standardName: "Bolt, Hex Head, M8 x 25 mm, Stainless A2",
    confidence: "High",
    reason: "Same thread (M8), same length (25 mm) and same material (A2 stainless).",
    masterCode: "FST-2210",
    rows: [
      { code: "FST-2210", name: "Hex bolt M8x25 A2 SS", brand: "", stock: 400, cost: 0.18 },
      { code: "FST-3019", name: "M8 X 25MM HEX HD BOLT STAINLESS", brand: "", stock: 250, cost: 0.21 },
    ],
  },
  {
    id: "G-0003",
    standardName: "Threadlocker, Loctite 243, 50 ml",
    confidence: "Medium",
    reason: "Same product and size. One line has no brand filled in, so please confirm.",
    masterCode: "CHM-0071",
    rows: [
      { code: "CHM-0071", name: "Loctite 243 threadlocker 50ml", brand: "Loctite", stock: 9, cost: 12.1 },
      { code: "CHM-0460", name: "Threadlock medium strength blue 243 50 ml", brand: "", stock: 6, cost: 11.4 },
    ],
  },
];

export const lookalikes: SampleLookalike[] = [
  {
    a: { code: "BRG-0388", name: "6205 2RS SKF bearing", brand: "SKF", stock: 18, cost: 4.35 },
    b: { code: "BRG-0143", name: "SKF 6205-ZZ Deep Groove Ball Bearing", brand: "SKF", stock: 10, cost: 3.8 },
    difference: "Seal type",
    detail: "2RS has rubber seals. ZZ has metal shields. They are not interchangeable in wet or dusty conditions.",
  },
  {
    a: { code: "BRG-0388", name: "6205 2RS SKF bearing", brand: "SKF", stock: 18, cost: 4.35 },
    b: { code: "BRG-0412", name: "SKF 6205-2RS/C3", brand: "SKF", stock: 4, cost: 5.1 },
    difference: "Internal clearance",
    detail: "C3 has a larger internal clearance, used for hotter or faster running. Same size, different part.",
  },
  {
    a: { code: "FST-2210", name: "Hex bolt M8x25 A2 SS", brand: "", stock: 400, cost: 0.18 },
    b: { code: "FST-2208", name: "Hex bolt M8x20 A2 SS", brand: "", stock: 300, cost: 0.16 },
    difference: "Length",
    detail: "25 mm and 20 mm long. Everything else matches.",
  },
];

export function groupStock(g: SampleGroup) {
  return g.rows.reduce((sum, r) => sum + r.stock, 0);
}

export function duplicateRows(g: SampleGroup) {
  return g.rows.filter((r) => r.code !== g.masterCode);
}

export function duplicateValue(g: SampleGroup) {
  return duplicateRows(g).reduce((sum, r) => sum + r.stock * r.cost, 0);
}

export const totals = {
  groups: groups.length,
  duplicateLines: groups.reduce((n, g) => n + duplicateRows(g).length, 0),
  unitsOnDuplicates: groups.reduce((n, g) => n + duplicateRows(g).reduce((s, r) => s + r.stock, 0), 0),
  valueOnDuplicates: groups.reduce((n, g) => n + duplicateValue(g), 0),
};

export const money = (n: number) =>
  n.toLocaleString("en-GB", { style: "currency", currency: "GBP", minimumFractionDigits: 2 });
