type CampaignRow = { name: string; id: string; spend: number; conversions: number };

function textCell(value: string) {
  // Campaign names must stay text when a spreadsheet opens the export.
  const safe = /^[=+\-@\t\r\n]/.test(value.trimStart()) || /^[\t\r\n]/.test(value) ? `'${value}` : value;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function campaignsCsv(campaigns: readonly CampaignRow[]) {
  const rows = campaigns.map((c) => [textCell(c.name), textCell(c.id), c.spend.toFixed(2).replace('.', ','), c.conversions].join(';'));
  return '\uFEFFКампания;ID;Расход (руб.);Конверсии\r\n' + rows.join('\r\n');
}
