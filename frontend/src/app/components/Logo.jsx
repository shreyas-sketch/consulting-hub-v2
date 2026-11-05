// AD × SK mark + product name: a brass-edged seal with the initials set in the serif, like a monogram on a file.
import brand from "@/brand";

export function LogoMark({ size = 36, className = "" }) {
  const [a, b] = brand.mark;
  return (
    <span aria-hidden className={`font-display shrink-0 inline-flex flex-col items-center justify-center rounded-[6px] bg-bz-gold text-bz-on-accent leading-none shadow-goldglow ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.3 }}>
      <span className="font-[600] tracking-[0.02em]">{a}</span>
      <span className="opacity-60" style={{ fontSize: size * 0.18, lineHeight: 0.9 }}>×</span>
      <span className="font-[600] tracking-[0.02em]">{b}</span>
    </span>
  );
}

export default function Logo({ className = "", word = "", big = false }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={big ? 44 : 36} />
      <span className={`flex flex-col leading-tight ${word}`}>
        <span className={`font-display font-[500] text-bz-ink whitespace-nowrap ${big ? "text-[24px]" : "text-[19px]"}`}>{brand.name}</span>
        <span className="text-[11px] font-semibold text-bz-gold whitespace-nowrap">Akshat Dani × Siddharth Kapoor</span>
      </span>
    </span>
  );
}
