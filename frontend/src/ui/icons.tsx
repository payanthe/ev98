import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ display: "block" }}
    >
      {children}
    </svg>
  );
}

export function IconSearch() {
  return (
    <Icon>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16.5 20 20.5" />
    </Icon>
  );
}

export function IconClose() {
  return (
    <Icon>
      <path d="M6 6l12 12M18 6 6 18" />
    </Icon>
  );
}

export function IconChevron({ direction }: { direction: "previous" | "next" }) {
  return (
    <Icon>
      <path d={direction === "previous" ? "M9 5l7 7-7 7" : "M15 5l-7 7 7 7"} />
    </Icon>
  );
}

export function IconPlus() {
  return (
    <Icon>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function IconMinus() {
  return (
    <Icon>
      <path d="M5 12h14" />
    </Icon>
  );
}

export function IconCheck() {
  return (
    <Icon>
      <path d="M5 12.5 9.2 17 19 7" />
    </Icon>
  );
}

export function IconFilter() {
  return (
    <Icon>
      <path d="M4 6h16M7 12h10M10 18h4" />
    </Icon>
  );
}

export function IconCar() {
  return (
    <Icon>
      <path d="M4 14.5 5.6 9.2A2 2 0 0 1 7.5 8h9a2 2 0 0 1 1.9 1.2L20 14.5" />
      <path d="M4 14.5h16v3.2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
      <path d="M7 18.7v1.1M17 18.7v1.1M7.2 14.5h.1M16.7 14.5h.1" />
    </Icon>
  );
}

export function IconBattery() {
  return (
    <Icon>
      <rect x="3.5" y="7.5" width="14.5" height="9" rx="2" />
      <path d="M18 10.5h1.5a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H18" />
      <path d="M6.5 10.5h6.5v3H6.5z" fill="currentColor" stroke="none" opacity="0.85" />
    </Icon>
  );
}

export function IconRange() {
  return (
    <Icon>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 13V8.5" />
      <path d="M12 13l3.6 2.2" />
      <path d="M7.2 7.2A8.4 8.4 0 0 1 16.8 7.2" />
    </Icon>
  );
}

export function IconBolt() {
  return (
    <Icon>
      <path d="M13 3.5 7.5 13h4.2L10.5 20.5 16.5 11h-4.1z" />
    </Icon>
  );
}

export function IconPlug() {
  return (
    <Icon>
      <path d="M9 7.5v3.5M15 7.5v3.5" />
      <path d="M8 11h8v2.2a4 4 0 0 1-4 4h0a4 4 0 0 1-4-4z" />
      <path d="M12 17.2V20.5" />
    </Icon>
  );
}

export function IconLocate() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="3.25" />
      <path d="M12 3.5v2.5M12 18v2.5M3.5 12H6M18 12h2.5" />
    </Icon>
  );
}

export function IconMapFit() {
  return (
    <Icon>
      <path d="M5 9V5h4M15 5h4v4M19 15v4h-4M9 19H5v-4" />
      <path d="M9.5 12h5M12 9.5v5" />
    </Icon>
  );
}

export function IconPin() {
  return (
    <Icon>
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </Icon>
  );
}

export function IconSources() {
  return (
    <Icon>
      <path d="M8 4.5h6.2L18 8.3V19.5H8z" />
      <path d="M14.2 4.5V8.3H18" />
      <path d="M10.5 12h5M10.5 15.5h5" />
    </Icon>
  );
}

export function IconOperator() {
  return (
    <Icon>
      <path d="M4.5 19.5h15" />
      <path d="M6.5 19.5V8.5l5.5-4 5.5 4v11" />
      <path d="M10 19.5v-4.5h4v4.5" />
      <path d="M9.5 11h1M13.5 11h1M9.5 14h1M13.5 14h1" />
    </Icon>
  );
}

export function IconPowerLevel({ level }: { level: 1 | 2 | 3 }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      aria-hidden="true"
      className={`power-level-icon level-${level}`}
    >
      <rect className="power-bar bar-1" x="3.5" y="14" width="4" height="6" rx="1.5" />
      <rect className="power-bar bar-2" x="10" y="9" width="4" height="11" rx="1.5" />
      <rect className="power-bar bar-3" x="16.5" y="4" width="4" height="16" rx="1.5" />
    </svg>
  );
}
