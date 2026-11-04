// AD × SK mark + product name. Drawn in HTML so it uses Manrope.
import brand from "@/brand";

export function LogoMark({ size = 36, className = "" }) {
  const [a, b] = brand.mark;
  return (
    <span aria-hidden className={`shrink-0 inline-flex flex-col items-center justify-center rounded-[10px] bg-bz-panel border border-bz-gold leading-none ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.27 }}>
      <span className="font-extrabold text-bz-gold tracking-[0.04em]">{a}</span>
      <span className="text-bz-rule font-medium" style={{ fontSize: size * 0.2, lineHeight: 1 }}>×</span>
      <span className="font-extrabold text-bz-gold tracking-[0.04em]">{b}</span>
    </span>
  );
}

export default function Logo({ className = "", word = "", big = false }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={big ? 44 : 36} />
      <span className={`flex flex-col leading-tight ${word}`}>
        <span className={`font-extrabold tracking-[-0.01em] text-bz-ink whitespace-nowrap ${big ? "text-[20px]" : "text-[16px]"}`}>{brand.name}</span>
        <span className="text-[10px] font-bold uppercase tracking-wordmark text-bz-gold whitespace-nowrap">AD × SK</span>
      </span>
    </span>
  );
}
