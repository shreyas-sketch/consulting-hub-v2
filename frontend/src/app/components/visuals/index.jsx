// Visual Builder renderers: <VisualSvg kind spec theme /> draws the stored spec as one clean SVG,
// downloadSvg / downloadPng export it (PNG = the SVG drawn to a canvas at 2x).
import Chart from "./Chart";
import { Comparison, Funnel, Matrix, MindMap, Process, Pyramid } from "./Diagrams";
import { THEMES } from "./theme";

export const KINDS = [
  { key: "matrix", label: "2x2 matrix", what: "Place options on two scales, like impact and ease.",
    example: "Place my five ideas for a ₹40 crore distributor on impact and ease: price rise, new warehouse, cash collection, hiring a sales head, cutting slow products." },
  { key: "process", label: "Process", what: "Steps in order, left to right.",
    example: "My five-step way of running a first client project, from the diagnosis call to the review after 90 days." },
  { key: "pyramid", label: "Pyramid", what: "Layers that build on each other.",
    example: "What a consulting practice is built on, from the base up: experience, a clear niche, an offer, proof, then referrals." },
  { key: "funnel", label: "Funnel", what: "Stages that narrow down, with your numbers.",
    example: "My client funnel last quarter: 200 conversations, 40 discovery calls, 10 proposals, 4 clients." },
  { key: "mindmap", label: "Mind map", what: "One idea, its branches and details.",
    example: "Why owner-led businesses stall at ₹50 crore: people, systems, cash, the owner's time." },
  { key: "comparison", label: "Comparison", what: "Options side by side on the same points.",
    example: "Compare hiring a consultant, hiring a full-time manager and doing it yourself, on cost, speed, risk and know-how." },
  { key: "chart", label: "Chart", what: "Bar, line or pie from numbers you paste.",
    example: "Monthly revenue for my client's stores, in ₹ lakh." },
];

export const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.key, k.label]));

export function VisualSvg({ kind, spec, theme = "dark" }) {
  const t = THEMES[theme] || THEMES.dark;
  if (!spec) return null;
  switch (kind) {
    case "matrix": return <Matrix s={spec} t={t} />;
    case "process": return <Process s={spec} t={t} />;
    case "pyramid": return <Pyramid s={spec} t={t} />;
    case "funnel": return <Funnel s={spec} t={t} />;
    case "mindmap": return <MindMap s={spec} t={t} />;
    case "comparison": return <Comparison s={spec} t={t} />;
    case "chart": return <Chart s={spec} t={t} />;
    default: return null;
  }
}

export { downloadPng, downloadSvg, fileName } from "./exportSvg";
