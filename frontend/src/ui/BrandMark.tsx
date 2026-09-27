import audi from "../assets/brands/audi.svg";
import bmw from "../assets/brands/bmw.svg";
import byd from "../assets/brands/byd.svg";
import honda from "../assets/brands/honda.svg";
import hyundai from "../assets/brands/hyundai.svg";
import mazda from "../assets/brands/mazda.svg";
import mercedes from "../assets/brands/mercedes-benz.svg";
import mitsubishi from "../assets/brands/mitsubishi.svg";
import toyota from "../assets/brands/toyota.svg";
import volkswagen from "../assets/brands/volkswagen.svg";
import volvo from "../assets/brands/volvo.svg";

const ICONS: Record<string, string> = {
  audi,
  bmw,
  byd,
  honda,
  hyundai,
  mazda,
  "mercedes-benz": mercedes,
  mitsubishi,
  toyota,
  volkswagen,
  volvo,
};

export function brandHasMark(icon: string | null | undefined): boolean {
  return Boolean(icon && ICONS[icon]);
}

export function BrandMark({ icon, name }: { icon: string | null; name: string }) {
  const src = icon ? ICONS[icon] : null;
  if (src) return <img className="brand-mark" src={src} alt="" />;
  const letter = name.trim().charAt(0).toUpperCase() || "•";
  return (
    <span className="brand-fallback" aria-hidden="true">
      {letter}
    </span>
  );
}
