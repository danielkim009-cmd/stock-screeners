/**
 * Export an array of plain objects as a CSV file download.
 * @param {Object[]} rows     - Array of result objects
 * @param {string[]} fields   - Ordered list of field keys to include
 * @param {Object}   headers  - { field: "Column Header" } display names
 * @param {string}   filename - Download filename (e.g. "turtle-2026-03-05.csv")
 */
export function exportCsv(rows, fields, headers, filename) {
  if (!rows || rows.length === 0) return;

  const escape = v => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? `"${s.replace(/"/g, '""')}"`
      : s;
  };

  const csvRows = [
    fields.map(f => escape(headers[f] ?? f)).join(","),
    ...rows.map(r => fields.map(f => escape(r[f])).join(",")),
  ];

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const today = () => new Date().toISOString().split("T")[0];
