import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const API_URL = "https://gen.emapna.com/api/evList/v2";
const outputDir = path.resolve("outputs/emapna_ev_dataset");
const pageSize = 50;

async function fetchPage(page) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      accept: "application/json, text/plain, */*",
      "content-type": "application/json",
      origin: "https://www.emapna.com",
      referer: "https://www.emapna.com/",
    },
    body: JSON.stringify({ page, limit: pageSize }),
  });
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  const payload = await response.json();
  if (!payload?.success || !Array.isArray(payload?.data?.evList)) {
    throw new Error(`Unexpected API response on page ${page}`);
  }
  return payload.data.evList;
}

const all = [];
for (let page = 0; page < 100; page += 1) {
  const pageRows = await fetchPage(page);
  all.push(...pageRows);
  if (pageRows.length < pageSize) break;
}

const byId = new Map();
for (const row of all) byId.set(String(row._id), row);
const rawRows = [...byId.values()].sort((a, b) => (a.priority ?? 9999) - (b.priority ?? 9999));

function flattenConnectors(value) {
  if (!Array.isArray(value)) return value == null ? [] : [String(value)];
  return value.flat(Infinity).flatMap((v) => {
    const text = String(v).trim();
    if (text.startsWith("[") && text.endsWith("]")) {
      try {
        const parsed = JSON.parse(text);
        return Array.isArray(parsed) ? parsed.map((x) => String(x).trim()) : [text];
      } catch {
        const recovered = ["Car-AC-GB/T", "Car-AC-Type1", "Car-AC-Type2", "Car-DC-GB/T", "Car-DC-CCS2", "Car-DC-CHAdeMO"].filter((token) => text.includes(token));
        if (/[,[]\s*"?-"?\s*\]$/.test(text) || text.includes(',-"')) recovered.push("-");
        return recovered.length ? recovered : [text];
      }
    }
    return [text];
  }).filter(Boolean);
}

function numbersFrom(value) {
  if (value == null) return [];
  return [...String(value).matchAll(/\d+(?:\.\d+)?/g)].map((m) => Number(m[0]));
}

const validConnectors = new Set([
  "Car-AC-GB/T",
  "Car-AC-Type1",
  "Car-AC-Type2",
  "Car-DC-GB/T",
  "Car-DC-CCS2",
  "Car-DC-CHAdeMO",
  "-",
]);

const rows = rawRows.map((r) => {
  const connectors = flattenConnectors(r.connectors);
  const battery = numbersFrom(r.batterySpecs);
  const range = numbersFrom(r.range);
  const voltage = numbersFrom(r.operatingVoltage);
  const unknown = connectors.filter((c) => !validConnectors.has(c));
  const nested = Array.isArray(r.connectors) && r.connectors.some(Array.isArray);
  const stringified = Array.isArray(r.connectors) && r.connectors.some((v) => typeof v === "string" && v.trim().startsWith("["));
  const issues = [];
  if (nested) issues.push("nested connector array normalized");
  if (stringified) issues.push("stringified connector array normalized");
  if (unknown.length) issues.push(`unknown connector: ${unknown.join(", ")}`);
  if (!r.brand || !r.model) issues.push("missing brand/model");
  if (battery.length === 0) issues.push("battery capacity not numeric");
  return {
    id: String(r._id ?? ""),
    priority: r.priority ?? null,
    brand: String(r.brand ?? "").trim(),
    model: String(r.model ?? "").trim(),
    evCarType: String(r.evCarType ?? "").trim(),
    importer: String(r.importer ?? "").trim(),
    batterySpecsRaw: String(r.batterySpecs ?? "").trim(),
    batteryKwhMin: battery.length ? Math.min(...battery) : null,
    batteryKwhMax: battery.length ? Math.max(...battery) : null,
    chargeLimit: String(r.chargeLimit ?? "").trim(),
    operatingVoltageRaw: String(r.operatingVoltage ?? "").trim(),
    operatingVoltageV: voltage.length ? voltage[0] : null,
    rangeRaw: String(r.range ?? "").trim(),
    rangeKm: range.length ? range[0] : null,
    rangeStandard: String(r.rangeStandard ?? "").trim(),
    connectors: connectors.filter((c) => c !== "-").join(", "),
    acGbt: connectors.includes("Car-AC-GB/T"),
    acType1: connectors.includes("Car-AC-Type1"),
    acType2: connectors.includes("Car-AC-Type2"),
    dcGbt: connectors.includes("Car-DC-GB/T"),
    dcCcs2: connectors.includes("Car-DC-CCS2"),
    dcChademo: connectors.includes("Car-DC-CHAdeMO"),
    noDcDeclared: connectors.includes("-"),
    rawConnectorsJson: JSON.stringify(r.connectors ?? []),
    dataQualityNotes: issues.join("; "),
  };
});

await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, "emapna_ev_api_raw.json"), JSON.stringify({ source: API_URL, fetchedAt: new Date().toISOString(), count: rawRows.length, evList: rawRows }, null, 2));

const columns = Object.keys(rows[0]);
const csvEscape = (value) => {
  if (value == null) return "";
  const text = typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const csv = [columns.join(","), ...rows.map((r) => columns.map((c) => csvEscape(r[c])).join(","))].join("\n") + "\n";
await fs.writeFile(path.join(outputDir, "emapna_ev_normalized.csv"), csv, "utf8");
await fs.writeFile(path.resolve("backend/app/data/vehicle_catalog.csv"), csv, "utf8");

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const vehicles = workbook.worksheets.add("Vehicles");
summary.showGridLines = false;
vehicles.showGridLines = false;
summary.tabColor = "#173F5F";
vehicles.tabColor = "#4C78A8";

const font = "Arial";
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["eMapna EV catalog"]];
summary.getRange("A2:F2").format.font = { name: font, size: 15, bold: true, color: "#173F5F" };
summary.getRange("A3:F3").format.borders = { bottom: { style: "thin", color: "#9FB3C8" } };
summary.getRange("A5:B11").values = [
  ["Metric", "Value"],
  ["Unique vehicles", rows.length],
  ["BEV", rows.filter((r) => r.evCarType === "BEV").length],
  ["PHEV", rows.filter((r) => r.evCarType === "PHEV").length],
  ["HEV", rows.filter((r) => r.evCarType === "HEV").length],
  ["EREV", rows.filter((r) => r.evCarType === "EREV").length],
  ["Records with data-quality notes", rows.filter((r) => r.dataQualityNotes).length],
];
summary.getRange("D5:F12").values = [
  ["Connector", "Vehicles", "Filter token"],
  ["AC GB/T", rows.filter((r) => r.acGbt).length, "AC GB/T"],
  ["AC Type 1", rows.filter((r) => r.acType1).length, "type 1"],
  ["AC Type 2", rows.filter((r) => r.acType2).length, "type 2"],
  ["DC GB/T", rows.filter((r) => r.dcGbt).length, "DC GB/T"],
  ["DC CCS2", rows.filter((r) => r.dcCcs2).length, "CCS2"],
  ["DC CHAdeMO", rows.filter((r) => r.dcChademo).length, "CHAdeMO"],
  ["No DC declared (-)", rows.filter((r) => r.noDcDeclared).length, "-"],
];
summary.getRange("A14:F17").values = [
  ["Source", API_URL, null, null, null, null],
  ["Request", "POST { page, limit } without connectorNames", null, null, null, null],
  ["Retrieved", new Date(), null, null, null, null],
  ["Note", "Raw API values are preserved. Normalized columns are mechanical parsing only; source naming errors are not silently corrected.", null, null, null, null],
];
summary.getRange("A5:B5").format = { fill: "#173F5F", font: { name: font, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("D5:F5").format = { fill: "#173F5F", font: { name: font, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("A5:F17").format.font = { name: font, size: 10 };
summary.getRange("A6:B11").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2EC" };
summary.getRange("D6:F12").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2EC" };
summary.getRange("B16").setNumberFormat("yyyy-mm-dd hh:mm");
summary.getRange("A14:A17").format.font = { name: font, size: 10, bold: true, color: "#334E68" };
summary.getRange("B17:F17").merge();
summary.getRange("B17:F17").format.wrapText = true;
summary.getRange("A1:F17").format.verticalAlignment = "center";
summary.getRange("A1:F17").format.autofitColumns();
summary.getRange("A1:F17").format.autofitRows();
summary.getRange("B:B").format.columnWidth = 38;
summary.getRange("D:D").format.columnWidth = 22;
summary.getRange("F:F").format.columnWidth = 16;

const headers = [
  "ID", "Priority", "Brand", "Model", "EV type", "Importer", "Battery (raw)", "Battery min (kWh)", "Battery max (kWh)",
  "Charge limit", "Voltage (raw)", "Voltage (V)", "Range (raw)", "Range (km)", "Range standard", "Connectors",
  "AC GB/T", "AC Type 1", "AC Type 2", "DC GB/T", "DC CCS2", "DC CHAdeMO", "No DC declared", "Raw connectors JSON", "Data-quality notes"
];
const matrix = rows.map((r) => [
  r.id, r.priority, r.brand, r.model, r.evCarType, r.importer, r.batterySpecsRaw, r.batteryKwhMin, r.batteryKwhMax,
  r.chargeLimit, r.operatingVoltageRaw, r.operatingVoltageV, r.rangeRaw, r.rangeKm, r.rangeStandard, r.connectors,
  r.acGbt, r.acType1, r.acType2, r.dcGbt, r.dcCcs2, r.dcChademo, r.noDcDeclared, r.rawConnectorsJson, r.dataQualityNotes
]);
vehicles.getRange("A1:Y1").values = [headers];
vehicles.getRange(`A2:Y${rows.length + 1}`).values = matrix;
const table = vehicles.tables.add(`A1:Y${rows.length + 1}`, true, "VehiclesTable");
table.style = "TableStyleMedium2";
vehicles.getRange("A1:Y1").format = { fill: "#173F5F", font: { name: font, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
vehicles.getRange(`A2:Y${rows.length + 1}`).format.font = { name: font, size: 9 };
vehicles.getRange(`A2:Y${rows.length + 1}`).format.verticalAlignment = "center";
vehicles.getRange(`B2:B${rows.length + 1}`).setNumberFormat("0");
vehicles.getRange(`H2:I${rows.length + 1}`).setNumberFormat("0.00");
vehicles.getRange(`L2:L${rows.length + 1}`).setNumberFormat("0");
vehicles.getRange(`N2:N${rows.length + 1}`).setNumberFormat("0");
vehicles.freezePanes.freezeRows(1);
vehicles.freezePanes.freezeColumns(4);
vehicles.getRange("A:Y").format.autofitColumns();
for (const col of ["A", "F", "P", "X", "Y"]) vehicles.getRange(`${col}:${col}`).format.columnWidth = col === "Y" ? 34 : 26;
vehicles.getRange(`F2:F${rows.length + 1}`).format.wrapText = true;
vehicles.getRange(`P2:P${rows.length + 1}`).format.wrapText = true;
vehicles.getRange(`X2:Y${rows.length + 1}`).format.wrapText = true;
vehicles.getRange(`A1:Y${rows.length + 1}`).format.autofitRows();

workbook.recalculate();
const summaryInspect = await workbook.inspect({ kind: "table", range: "Summary!A1:F17", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 8 });
console.log(summaryInspect.ndjson);
const vehicleInspect = await workbook.inspect({ kind: "table", range: "Vehicles!A1:Y8", include: "values,formulas", tableMaxRows: 8, tableMaxCols: 25 });
console.log(vehicleInspect.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);
const preview = await workbook.render({ sheetName: "Summary", range: "A1:F17", scale: 1.5, format: "png" });
await fs.writeFile(path.join(outputDir, "emapna_ev_summary_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "emapna_ev_complete.xlsx"));

console.log(JSON.stringify({ outputDir, rawCount: all.length, uniqueCount: rows.length, columns: headers.length }));
