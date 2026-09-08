import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer";
import QRCode from "qrcode";
import { fileURLToPath } from "node:url";
import { PDFDocument } from "pdf-lib";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const defaultDataPath = path.join(__dirname, "data.json");
const templatePath = path.join(__dirname, "report.html");
const summaryTemplatePath = path.join(__dirname, "summary.html");
const introTemplatePath = path.join(__dirname, "intro.html");
const ancestryTemplatePath = path.join(__dirname, "ancestry.html");
const rsidTemplatePath = path.join(__dirname, "rsid.html");
const coverTemplatePath = path.join(__dirname, "cover.html");
const closingTemplatePath = path.join(__dirname, "closing.html");
const indexTemplatePath = path.join(__dirname, "index.html");
const coverSectionTemplatePath = path.join(__dirname, "cover_section.html");

const bgPath = path.join(__dirname, "assets", "dna-bg-two.png");
const coverBgPath = path.join(__dirname, "assets", "dna-bg.png");
const logoColorPath = path.join(__dirname, "assets", "genomiacolor.png");
const logoPath = path.join(__dirname, "assets", "genomia.png");

const maxItemsPerCategoryRaw = Number.parseInt(
  process.env.REPORT_MAX_ITEMS_PER_CATEGORY || "0",
  10
);
const maxItemsPerCategory = 
  Number.isFinite(maxItemsPerCategoryRaw) && maxItemsPerCategoryRaw > 0
    ? maxItemsPerCategoryRaw
    : 0;
const skipRsidPages = process.env.REPORT_SKIP_RSID_PAGES === "1";

const pdfScaleRaw = Number.parseFloat(process.env.REPORT_PDF_SCALE || "1");
const pdfScale = 
  Number.isFinite(pdfScaleRaw) && pdfScaleRaw > 0 ? pdfScaleRaw : 1;

const enableSingleProcess = process.env.REPORT_SINGLE_PROCESS === "1";

const chromiumArgs = [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-dev-shm-usage",
  "--disable-gpu",
  "--disable-extensions",
  "--disable-background-networking",
  "--disable-default-apps",
  "--disable-sync",
  "--metrics-recording-only",
  "--mute-audio",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-features=IsolateOrigins,site-per-process",
  "--renderer-process-limit=2",
];

if (enableSingleProcess) {
  chromiumArgs.push("--no-zygote", "--single-process");
}

const browserExecutableCandidates = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];

function resolveBrowserExecutablePath() {
  for (const candidate of browserExecutableCandidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return "";
}

function shouldRetryBrowser(err) {
  if (!err) return false;
  const message = [
    err.message,
    err.cause?.message,
    typeof err === "string" ? err : "",
  ]
    .filter(Boolean)
    .join(" ");
  return /Target closed|TargetCloseError|Connection closed|ConnectionClosedError|Protocol error/i.test(
    message
  );
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const current = argv[i];
    if (current === "--input") {
      args.input = argv[i + 1];
      i += 1;
    } else if (current === "--out-dir") {
      args.outDir = argv[i + 1];
      i += 1;
    } else if (current === "--manifest") {
      args.manifest = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function fileToDataUrl(filePath, mime = "image/png") {
  if (!fs.existsSync(filePath)) return "";
  const buf = fs.readFileSync(filePath);
  return `data:${mime};base64,${buf.toString("base64")}`;
}

function pct(n, total) {
  if (!total) return 0;
  return Math.round((n / total) * 100);
}

function getQuickChartUrl({ high, mid, low }) {
  const chartConfig = {
    type: "doughnut",
    data: {
      labels: ["Alto", "Medio", "Bajo"],
      datasets: [
        {
          data: [high, mid, low],
          backgroundColor: ["#ef4444", "#f97316", "#10b981"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      cutoutPercentage: 70,
      legend: { display: false },
      plugins: { datalabels: { display: false } },
    },
  };
  const jsonStr = JSON.stringify(chartConfig);
  return `https://quickchart.io/chart?c=${encodeURIComponent(jsonStr)}&w=300&h=300`;
}

function normalizeText(value) {
  if (!value) return "";
  return String(value)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function normalizeCategory(value) {
  const norm = normalizeText(value);
  if (!norm) return "";
  if (norm.includes("enfermedad")) return "enfermedades";
  if (norm.includes("farmaco")) return "farmacogenetica";
  if (norm.includes("biomarc")) return "biomarcadores";
  if (norm.includes("biometr")) return "biometricas";
  if (norm.includes("rasgo")) return "rasgos";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function fillTemplate(tpl, vars) {
  let html = tpl.replace(/<link[^>]*fonts.googleapis[^>]*>/gi, "")
                .replace(/<link[^>]*fonts.gstatic[^>]*>/gi, "");
  
  for (const [key, value] of Object.entries(vars)) {
    const safeValue = value === undefined || value === null ? "" : String(value);
    html = html.replaceAll(`{{${key}}}`, safeValue);
  }
  return html;
}

function safeText(value, fallback = "N/A") {
  if (value === undefined || value === null) return fallback;
  const text = String(value).trim();
  return text.length ? text : fallback;
}

function formatPercent(value) {
  if (value === undefined || value === null || value === "") {
    return { display: "N/A", width: "0%", pos: "0%" };
  }
  const cleaned = String(value).replace("%", "").trim();
  const num = Number(cleaned);
  if (!Number.isFinite(num)) {
    return { display: String(value), width: "0%", pos: "0%" };
  }
  const clamped = Math.max(0, Math.min(100, num));
  const widthValue = clamped <= 0 ? 0 : Math.max(2, clamped);
  const posValue = Math.max(2, Math.min(98, clamped));
  const display = Number.isInteger(clamped) ? `${clamped}%` : `${clamped.toFixed(1)}%`;
  return { display, width: `${widthValue}%`, pos: `${posValue}%` };
}

function formatRisk(value) {
  const raw = safeText(value, "No definido");
  const normalized = raw.toLowerCase();
  if (normalized.startsWith("alto") || normalized === "high") {
    return { label: "Alto", className: "risk-high" };
  }
  if (
    normalized.startsWith("medio") ||
    normalized.startsWith("inter") ||
    normalized === "medium" ||
    normalized === "mid"
  ) {
    return { label: "Medio", className: "risk-mid" };
  }
  if (normalized.startsWith("bajo") || normalized === "low") {
    return { label: "Bajo", className: "risk-low" };
  }
  return { label: raw, className: "risk-unknown" };
}

function riskPriority(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.startsWith("alto") || normalized === "high") return 3;
  if (
    normalized.startsWith("medio") ||
    normalized.startsWith("inter") ||
    normalized === "medium" ||
    normalized === "mid"
  ) {
    return 2;
  }
  if (normalized.startsWith("bajo") || normalized === "low") return 1;
  return 0;
}

function safeFileSegment(value, fallback) {
  const cleaned = String(value || "")
    .replace(/[^a-zA-Z0-9_-]/g, "")
    .trim();
  return cleaned.length ? cleaned : fallback;
}

function formatSectionNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value ?? "");
  return String(num).padStart(2, "0");
}

function buildIndexRows(entries) {
  return entries
    .map((entry) => {
      const number = escapeHtml(entry.number ?? "");
      const label = escapeHtml(entry.label ?? "");
      const page = escapeHtml(entry.page ?? "");
      return (
        `
        <div class="toc-row">
          <div class="toc-number">${number}</div>
          <div class="toc-title">${label}</div>
          <div class="toc-page">${page}</div>
        </div>
      `
      );
    })
    .join("");
}

function interpolateColor(score) {
  const c1 = [124, 58, 237];
  const c2 = [59, 130, 246];
  const c3 = [6, 182, 212];

  const { start, end, t } = score <= 50
    ? { start: c1, end: c2, t: score / 50 }
    : { start: c2, end: c3, t: (score - 50) / 50 };

  const r = Math.round(start[0] + (end[0] - start[0]) * t);
  const g = Math.round(start[1] + (end[1] - start[1]) * t);
  const b = Math.round(start[2] + (end[2] - start[2]) * t);

  return `rgb(${r}, ${g}, ${b})`;
}

const icons = {
  heart: '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
  dna: '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h5"></path><path d="M17 12h5"></path><path d="M9 12h6"></path><path d="M12 2v20"></path><path d="M4.93 19.07l4.24-4.24"></path><path d="M14.83 9.17l4.24-4.24"></path><path d="M14.83 14.83l4.24 4.24"></path><path d="M4.93 4.93l4.24 4.24"></path></svg>',
  pill: '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 20.5l10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7z"></path><path d="M8.5 8.5l7 7"></path></svg>',
  eye: '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
  body: '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
};

const categoryOrder = [
  "enfermedades",
  "farmacogenetica",
  "biometricas",
  "biomarcadores",
  "rasgos",
];

const summaryPageSize = 16;

const categoryMeta = {
  enfermedades: {
    label: "Enfermedades",
    icon: icons.heart,
    color: "#ef4444",
    gradient: "linear-gradient(135deg, #ef4444, #dc2626)",
  },
  farmacogenetica: {
    label: "Farmacogenetica",
    icon: icons.pill,
    color: "#8b5cf6",
    gradient: "linear-gradient(135deg, #8b5cf6, #7c3aed)",
  },
  biomarcadores: {
    label: "Biomarcadores",
    icon: icons.dna,
    color: "#10b981",
    gradient: "linear-gradient(135deg, #10b981, #059669)",
  },
  biometricas: {
    label: "Biometricas",
    icon: icons.body,
    color: "#0ea5e9",
    gradient: "linear-gradient(135deg, #0ea5e9, #0284c7)",
  },
  rasgos: {
    label: "Rasgos",
    icon: icons.eye,
    color: "#f59e0b",
    gradient: "linear-gradient(135deg, #f59e0b, #d97706)",
  },
};

const riskBadgeStyles = {
  Alto: { bg: "#fef2f2", color: "#ef4444", border: "#fee2e2" },
  Medio: { bg: "#fff7ed", color: "#f97316", border: "#fed7aa" },
  Bajo: { bg: "#ecfdf5", color: "#10b981", border: "#d1fae5" },
};

function buildAncestrySummary(top5) {
  const list = Array.isArray(top5) ? top5 : [];
  const main = list[0] || { country: "N/A", pct: 0 };
  const others = list.slice(1, 5);
  const rowsHtml = others
    .map((item) => {
      const name = escapeHtml(item.country ?? "N/A");
      const pctValue = Number(item.pct);
      const safePct = Number.isFinite(pctValue) ? pctValue : 0;
      return (
        `
        <div class="ancestry-row">
          <div class="ancestry-name">${name}</div>
          <div class="ancestry-val">${safePct}%</div>
        </div>
      `
      );
    })
    .join("");

  return {
    mainCountry: escapeHtml(main.country ?? "N/A"),
    mainPct: Number.isFinite(Number(main.pct)) ? Number(main.pct) : 0,
    rowsHtml,
  };
}

function buildHighlights(items, limit = 4) {
  const sorted = items
    .slice()
    .sort((a, b) => {
      const riskDiff = riskPriority(b.riesgo) - riskPriority(a.riesgo);
      if (riskDiff !== 0) return riskDiff;
      const magA = Number(a.magnitudEfecto) || 0;
      const magB = Number(b.magnitudEfecto) || 0;
      return magB - magA;
    });

  const selected = sorted.slice(0, limit);
  if (!selected.length) {
    return (
      `
      <div class="highlight-item" style="border-left-color: #cbd5e1;">
        <div class="highlight-icon" style="background: linear-gradient(135deg, #cbd5e1, #94a3b8);">
          ${icons.dna}
        </div>
        <div class="highlight-content">
          <div class="highlight-name">Sin hallazgos relevantes</div>
          <div class="highlight-category">No hay datos disponibles</div>
        </div>
      </div>
    `
    );
  }

  return selected
    .map((item) => {
      const categoryKey = normalizeCategory(item.categoria) || item.categoria;
      const meta = categoryMeta[categoryKey] || {
        label: "Sin clasificar",
        icon: icons.dna,
        color: "#64748b",
        gradient: "linear-gradient(135deg, #94a3b8, #64748b)",
      };
      const risk = formatRisk(item.riesgo);
      const badgeStyle = riskBadgeStyles[risk.label] || riskBadgeStyles.Bajo;
      const name = escapeHtml(safeText(item.fenotipo));
      const categoryLabel = escapeHtml(meta.label);

      return (
        `
        <div class="highlight-item" style="border-left-color: ${meta.color};">
          <div class="highlight-icon" style="background: ${meta.gradient};">
            ${meta.icon}
          </div>
          <div class="highlight-content">
            <div class="highlight-name">${name}</div>
            <div class="highlight-category">${categoryLabel}</div>
          </div>
          <div class="highlight-badge" style="background: ${badgeStyle.bg}; color: ${badgeStyle.color}; border: 1px solid ${badgeStyle.border};">
            ${risk.label.toUpperCase()}
          </div>
        </div>
      `
      );
    })
    .join("");
}

function buildAreasOverview(areas) {
  const safeAreas = areas || {};
  return categoryOrder
    .map((key) => {
      const meta = categoryMeta[key] || { label: key };
      const counts = safeAreas[key]?.counts || { high: 0, mid: 0, low: 0 };
      const high = Number(counts.high) || 0;
      const mid = Number(counts.mid) || 0;
      const low = Number(counts.low) || 0;

      return (
        `
        <div class="area-card">
          <div class="area-title">${escapeHtml(meta.label)}</div>
          <div class="area-counts">
            <div class="area-count high">${high}</div>
            <div class="area-count mid">${mid}</div>
            <div class="area-count low">${low}</div>
          </div>
        </div>
      `
      );
    })
    .join("");
}

function buildSummaryContent(items) {
  if (!items.length) {
    return (
      `
      <div class="disease-empty">
        Sin hallazgos relevantes para esta seccion.
      </div>
    `
    );
  }

  return items
    .map((item) => {
      const risk = formatRisk(item.riesgo);
      const badgeClass =
        risk.className === "risk-high"
          ? "badge-high"
          : risk.className === "risk-mid"
          ? "badge-mid"
          : "badge-low";
      const name = escapeHtml(safeText(item.fenotipo));
      const metaValue = escapeHtml(safeText(item.rsid));

      return (
        `
        <div class="disease-card ${risk.className}">
          <div class="disease-badge ${badgeClass}">${risk.label.toUpperCase()}</div>
          <div class="disease-info">
            <div class="disease-name">${name}</div>
            <div class="disease-meta">Marcador ${metaValue}</div>
          </div>
        </div>
      `
      );
    })
    .join("");
}

function chunkItems(items, size) {
  const chunks = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks.length ? chunks : [[]];
}

function rebalanceChunks(chunks) {
  if (chunks.length < 2) return chunks;
  const last = chunks[chunks.length - 1];
  if (last.length !== 1) return chunks;
  const prev = chunks[chunks.length - 2];
  const combined = prev.concat(last);
  const splitIndex = Math.ceil(combined.length / 2);
  const balancedPrev = combined.slice(0, splitIndex);
  const balancedLast = combined.slice(splitIndex);
  return [...chunks.slice(0, -2), balancedPrev, balancedLast];
}

// === TEMPLATE PARSING HELPERS ===
function parseHtmlTemplate(htmlContent) {
  const headMatch = htmlContent.match(/<head>([\s\S]*?)<\/head>/i);
  const bodyMatch = htmlContent.match(/<body>([\s\S]*?)<\/body>/i);
  const headContent = headMatch ? headMatch[1] : "";
  const bodyContent = bodyMatch ? bodyMatch[1] : "";

  // Extract style
  const styleMatch = headContent.match(/<style>([\s\S]*?)<\/style>/i);
  const styleContent = styleMatch ? styleMatch[1] : "";
  const otherHead = headContent.replace(/<style>[\s\S]*?<\/style>/i, "");

  return { otherHead, styleContent, bodyContent };
}

// Concurrency helper
async function runWithLimit(items, limit, fn) {
  const results = [];
  const executing = [];
  for (const item of items) {
    const p = Promise.resolve().then(async () => {
        const res = await fn(item);
        // Small pause to allow GC to catch up
        if (global.gc) global.gc(); 
        await new Promise(r => setTimeout(r, 100));
        return res;
    });
    results.push(p);
    const e = p.then(() => executing.splice(executing.indexOf(e), 1));
    executing.push(e);
    if (executing.length >= limit) {
      await Promise.race(executing);
    }
  }
  return Promise.all(results);
}

// === MAIN ===
const args = parseArgs(process.argv.slice(2));
const inputPath = args.input || defaultDataPath;
const outDir = args.outDir || path.join(__dirname, "out");
const manifestPath = args.manifest || "";

const data = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
const template = fs.readFileSync(templatePath, "utf-8");
const summaryTemplate = fs.readFileSync(summaryTemplatePath, "utf-8");
const introTemplate = fs.readFileSync(introTemplatePath, "utf-8");
const ancestryTemplate = fs.readFileSync(ancestryTemplatePath, "utf-8");
const rsidTemplate = fs.readFileSync(rsidTemplatePath, "utf-8");
const coverTemplate = fs.readFileSync(coverTemplatePath, "utf-8");
const closingTemplate = fs.readFileSync(closingTemplatePath, "utf-8");
const indexTemplate = fs.readFileSync(indexTemplatePath, "utf-8");
const coverSectionTemplate = fs.readFileSync(coverSectionTemplatePath, "utf-8");

fs.mkdirSync(outDir, { recursive: true });

const bgDataUrl = fileToDataUrl(bgPath, "image/png");
const coverBgDataUrl = fileToDataUrl(coverBgPath, "image/png") || bgDataUrl;
const logoDataUrl = fileToDataUrl(logoPath, "image/png") || fileToDataUrl(logoColorPath, "image/png");
const logoColorDataUrl = fileToDataUrl(logoColorPath, "image/png") || logoDataUrl;

// Parse RSID Template for batching
const { otherHead: rsidHead, styleContent: rsidStyle, bodyContent: rsidBody } = parseHtmlTemplate(rsidTemplate);
const rsidMultiPageStyle = `
  ${rsidStyle}
  html, body { height: auto !important; display: block !important; background: #f8fafc; }
  .rsid-page { width: 210mm; height: 297mm; position: relative; overflow: hidden; background: #f8fafc; margin: 0; padding: 0; display: flex; flex-direction: column; page-break-after: always; }
  .rsid-page:last-child { page-break-after: auto; }
`;
const rsidMasterTemplateStart = `<!doctype html><html lang="es"><head>${rsidHead}<style>${rsidMultiPageStyle}</style></head><body>`;
const rsidMasterTemplateEnd = `</body></html>`;

(async () => {
  const executablePath = resolveBrowserExecutablePath();
  const launchOptions = { args: chromiumArgs };
  if (executablePath) launchOptions.executablePath = executablePath;
  const createBrowser = () => puppeteer.launch(launchOptions);
  
  const safeCloseBrowser = async (browserInstance) => {
    if (!browserInstance) return;
    try {
      await browserInstance.close();
    } catch {
      // Ignore close errors
    }
  };

  const browserRef = { current: await createBrowser() };
  
  const renderPdfSafe = async (html, options = {}) => {
    let page;
    try {
        page = await browserRef.current.newPage();
        // OPTIMIZATION: Allow cache to potentially reuse assets between pages
        // await page.setCacheEnabled(false); 
        await page.setContent(html, { waitUntil: "domcontentloaded", timeout: 60000 });
        if (options.waitForSelector) {
            await page.waitForSelector(options.waitForSelector, { timeout: 30000 }).catch(() => {});
        }
        return await page.pdf({
            format: "A4",
            printBackground: true,
            scale: pdfScale,
            margin: { top: 0, right: 0, bottom: 0, left: 0 },
        });
    } catch (err) {
        if (shouldRetryBrowser(err)) {
            try { await browserRef.current.close(); } catch {}
            browserRef.current = await createBrowser();
            page = await browserRef.current.newPage();
            await page.setContent(html, { waitUntil: "domcontentloaded", timeout: 60000 });
            return await page.pdf({ format: "A4", printBackground: true });
        }
        throw err;
    } finally {
        if (page) try { await page.close(); } catch {}
    }
  };

  const manifest = { reports: [] };

  for (const person of data.people || []) {
    const masterPdfDoc = await PDFDocument.create();
    
    // Preparation logic
    const reportId = safeFileSegment(person.reportId, "reporte");
    const reportLabel = person.reportId || reportId;
    // ... (Stats calculation)
    const snpsAnalyzed = person.summary?.snpsAnalyzed ?? 0;
    const highCount = person.summary?.riskCounts?.high ?? 0;
    const midCount = person.summary?.riskCounts?.mid ?? 0;
    const lowCount = person.summary?.riskCounts?.low ?? 0;
    const totalRelevant = highCount + midCount + lowCount || 1;
    const highPct = pct(highCount, totalRelevant);
    const midPct = pct(midCount, totalRelevant);
    const lowPct = pct(lowCount, totalRelevant);
    const coveragePct = snpsAnalyzed ? Math.min(100, Math.round((totalRelevant / snpsAnalyzed) * 100)) : 0;
    const geneticScore = Math.max(0, Math.min(100, Math.round(100 - (highPct * 1.5 + midPct * 0.3))));
    const markerBorderColor = interpolateColor(geneticScore);
    
    const chartUrl = getQuickChartUrl({ high: highCount, mid: midCount, low: lowCount });
    let donutUrl = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
    try {
        const chartRes = await fetch(chartUrl);
        if (chartRes.ok) donutUrl = `data:image/png;base64,${Buffer.from(await chartRes.arrayBuffer()).toString("base64")}`;
    } catch {}

    const ancestryInfo = buildAncestrySummary(person.ancestryTop5 || []);
    const highlightsHtml = buildHighlights(person.rsids || []);
    const areasOverviewHtml = buildAreasOverview(person.areas);
    const qrDataUrl = person.link ? await QRCode.toDataURL(person.link, { margin: 1, width: 256 }) : "";

    const rsidItems = Array.isArray(person.rsids) ? person.rsids : [];
    const rsidsByCategory = Object.fromEntries(categoryOrder.map((key) => [key, []]));
    for (const rawItem of rsidItems) {
      const item = rawItem || {};
      const key = normalizeCategory(item.categoria) || item.categoria;
      if (key && rsidsByCategory[key]) rsidsByCategory[key].push(item);
    }

    const categoryData = categoryOrder.map((categoryKey, index) => {
        const items = rsidsByCategory[categoryKey] || [];
        let counts = person.areas?.[categoryKey]?.counts || null;
        if (!counts) {
            counts = { high: 0, mid: 0, low: 0 };
            for (const item of items) {
                const risk = formatRisk(item.riesgo ?? item.risk);
                if (risk.className === "risk-high") counts.high++;
                else if (risk.className === "risk-mid") counts.mid++;
                else counts.low++;
            }
        }
        const sortedItems = items.slice().sort((a, b) => {
            const riskDiff = riskPriority(b.riesgo) - riskPriority(a.riesgo);
            if (riskDiff !== 0) return riskDiff;
            return (Number(b.magnitudEfecto)||0) - (Number(a.magnitudEfecto)||0);
        });
        const limitedItems = maxItemsPerCategory > 0 ? sortedItems.slice(0, maxItemsPerCategory) : sortedItems;
        const rsidItems = skipRsidPages ? [] : limitedItems;
        const summaryChunks = rebalanceChunks(chunkItems(limitedItems, summaryPageSize));
        return { categoryKey, counts, sortedItems, rsidItems, summaryChunks, sectionMeta: categoryMeta[categoryKey] || { label: categoryKey }, sectionNumber: formatSectionNumber(3 + index) };
    });

    const totalNumberedPages = 1 + 1 + 1 + categoryData.reduce((sum, entry) => sum + 1 + entry.summaryChunks.length + entry.rsidItems.length, 0) + 1;
    let numberedPage = 0;
    const nextNumberedPage = () => { numberedPage++; return numberedPage; };

    // --- Build Task List ---
    const tasks = [];
    
    // 1. Cover
    tasks.push(async () => {
        const html = fillTemplate(coverTemplate, {
            bgDataUrl: coverBgDataUrl, logoDataUrl, name: escapeHtml(person.displayName ?? person.name ?? ""),
            reportId: escapeHtml(reportLabel), date: escapeHtml(person.date ?? ""), qrDataUrl,
        });
        return { order: 0, buffer: await renderPdfSafe(html) };
    });

    // 2. Index
    let displayPage = 1;
    const tocEntries = [
        { target: "intro", label: "Introduccion", number: formatSectionNumber(1), page: displayPage++ },
        { target: "report", label: "Resumen genetico", number: formatSectionNumber(2), page: displayPage++ },
        { target: "ancestry", label: "Ancestria", number: formatSectionNumber(2), page: displayPage++ }
    ];
    for (const d of categoryData) {
        tocEntries.push({ target: `section-${d.categoryKey}`, label: d.sectionMeta.label, number: d.sectionNumber, page: displayPage });
        displayPage += 1 + d.summaryChunks.length + d.rsidItems.length;
    }
    tocEntries.push({ target: "closing", label: "Cierre", number: "FIN", page: displayPage });

    tasks.push(async () => {
        const html = fillTemplate(indexTemplate, { indexRowsHtml: buildIndexRows(tocEntries) });
        return { order: 1, buffer: await renderPdfSafe(html) };
    });

    // 3. Intro
    const introPageNum = nextNumberedPage();
    tasks.push(async () => {
        const html = fillTemplate(introTemplate, {
            bgDataUrl, logoColorDataUrl, heroNumber: formatSectionNumber(1), reportId: escapeHtml(reportLabel),
            date: escapeHtml(person.date ?? ""), pageNumber: introPageNum, pageTotal: totalNumberedPages,
        });
        return { order: 2, buffer: await renderPdfSafe(html) };
    });

    // 4. Report
    const reportPageNum = nextNumberedPage();
    tasks.push(async () => {
        const html = fillTemplate(template, {
            bgDataUrl, logoColorDataUrl, heroNumber: formatSectionNumber(2), name: escapeHtml(person.name ?? ""),
            displayName: escapeHtml(person.displayName ?? person.name ?? ""), reportId: escapeHtml(reportLabel),
            date: escapeHtml(person.date ?? ""), snpsAnalyzed, highCount, midCount, lowCount, highPct, midPct, lowPct,
            coveragePct, donutUrl, geneticScore, markerBorderColor, ancestryMainCountry: ancestryInfo.mainCountry,
            ancestryMainPct: ancestryInfo.mainPct, ancestrySecondaryRows: ancestryInfo.rowsHtml, highlightsHtml,
            areasOverviewHtml, pageNumber: reportPageNum, pageTotal: totalNumberedPages,
        });
        return { order: 3, buffer: await renderPdfSafe(html) };
    });

    // 5. Ancestry
    const ancestryPageNum = nextNumberedPage();
    const ancestryDataJson = JSON.stringify(person.ancestryMap || {});
    const indigenousDataJson = JSON.stringify(person.indigenousData || []);
    tasks.push(async () => {
        const html = fillTemplate(ancestryTemplate, {
            bgDataUrl, logoColorDataUrl, heroNumber: formatSectionNumber(2), reportId: escapeHtml(reportLabel),
            date: escapeHtml(person.date ?? ""), ancestryDataJson, indigenousDataJson,
            pageNumber: ancestryPageNum, pageTotal: totalNumberedPages,
        });
        return { order: 4, buffer: await renderPdfSafe(html, { waitForSelector: ".country" }) };
    });

    let globalOrder = 5;

    // 6. Categories
    for (const data of categoryData) {
        const secPageNum = nextNumberedPage();
        const localOrder = globalOrder++;
        tasks.push(async () => {
            const html = fillTemplate(coverSectionTemplate, {
                sectionNumber: data.sectionNumber, sectionTitle: escapeHtml(data.sectionMeta.label),
                pageNumber: secPageNum, pageTotal: totalNumberedPages,
            });
            return { order: localOrder, buffer: await renderPdfSafe(html) };
        });

        for (const chunk of data.summaryChunks) {
            const sumPageNum = nextNumberedPage();
            const sumOrder = globalOrder++;
            tasks.push(async () => {
                const html = fillTemplate(summaryTemplate, {
                    bgDataUrl, logoColorDataUrl, sectionNumber: data.sectionNumber, sectionTitle: data.sectionMeta.label,
                    sectionSubtitle: `Resumen de variantes en ${data.sectionMeta.label} con su nivel de riesgo estimado.`, 
                    sectionHigh: data.counts.high ?? 0, sectionMid: data.counts.mid ?? 0, sectionLow: data.counts.low ?? 0,
                    summaryContent: buildSummaryContent(chunk), reportId: escapeHtml(reportLabel),
                    date: escapeHtml(person.date ?? ""), pageNumber: sumPageNum, pageTotal: totalNumberedPages,
                });
                return { order: sumOrder, buffer: await renderPdfSafe(html) };
            });
        }

        if (data.rsidItems.length > 0) {
            const RSID_CHUNK_SIZE = 10;
            const chunks = chunkItems(data.rsidItems, RSID_CHUNK_SIZE);
            for (const chunk of chunks) {
                const pagesData = chunk.map(item => ({ item, pageNum: nextNumberedPage() }));
                const chunkOrder = globalOrder++;
                tasks.push(async () => {
                    let inner = "";
                    for (const { item, pageNum } of pagesData) {
                        const pctInfo = formatPercent(item.porcentajeChilenos);
                        const risk = formatRisk(item.riesgo ?? item.risk);
                        const catLabel = data.sectionMeta.label || safeText(item.categoria, "Sin clasificar");
                        const pageHtml = fillTemplate(rsidBody, {
                            heroNumber: "RS", rsid: escapeHtml(safeText(item.rsid)), phenotype: escapeHtml(safeText(item.fenotipo)),
                            phenotypeDescription: escapeHtml(safeText(item.phenotypeDescription, "N/D")), category: escapeHtml(catLabel),
                            riskLabel: escapeHtml(risk.label), riskClass: risk.className, source: escapeHtml(safeText(item.fuente)),
                            chilePercentDisplay: pctInfo.display, chilePercentWidth: pctInfo.width, chilePercentPos: pctInfo.pos,
                            refAllele: escapeHtml(safeText(item.aleloReferencia)), altAllele: escapeHtml(safeText(item.aleloAlternativo)),
                            chromosome: escapeHtml(safeText(item.cromosoma)), position: escapeHtml(safeText(item.posicion)),
                            pageNumber: pageNum, pageTotal: totalNumberedPages,
                        });
                        inner += `<div class="rsid-page">${pageHtml}</div>`;
                    }
                    const fullHtml = `${rsidMasterTemplateStart}${inner}${rsidMasterTemplateEnd}`;
                    return { order: chunkOrder, buffer: await renderPdfSafe(fullHtml) };
                });
            }
        }
    }

    // 7. Closing
    const closingPageNum = nextNumberedPage();
    const closingOrder = globalOrder++;
    tasks.push(async () => {
        const html = fillTemplate(closingTemplate, {
            bgDataUrl: coverBgDataUrl, logoDataUrl, displayName: escapeHtml(person.displayName ?? person.name ?? ""),
            reportId: escapeHtml(reportLabel), date: escapeHtml(person.date ?? ""), link: escapeHtml(person.link ?? ""),
            qrDataUrl, pageNumber: closingPageNum, pageTotal: totalNumberedPages,
        });
        return { order: closingOrder, buffer: await renderPdfSafe(html) };
    });

    // === EXECUTE PARALLEL ===
    const CONCURRENCY_LIMIT = 1; // Limit 1 for 512MB RAM stability in production
    const results = await runWithLimit(tasks, CONCURRENCY_LIMIT, t => t());
    results.sort((a, b) => a.order - b.order);

    for (const res of results) {
        const chunkDoc = await PDFDocument.load(res.buffer);
        const copied = await masterPdfDoc.copyPages(chunkDoc, chunkDoc.getPageIndices());
        copied.forEach(p => masterPdfDoc.addPage(p));
    }

    const finalBytes = await masterPdfDoc.save();
    const finalPath = path.join(outDir, `${reportId}_completo.pdf`);
    fs.writeFileSync(finalPath, finalBytes);
    
    manifest.reports.push({ reportId, files: [path.resolve(finalPath)], tocEntries, isMerged: true });
  }

  await safeCloseBrowser(browserRef.current);
  if (manifestPath) fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
})().catch(err => {
  console.error("Error:", err);
  process.exit(1);
});
