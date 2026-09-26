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

export function IconCar() {
  return (
    <Icon>
      <path d="M4 14.5 5.6 9.2A2 2 0 0 1 7.5 8h9a2 2 0 0 1 1.9 1.2L20 14.5" />
      <path d="M4 14.5h16v3.2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
      <path d="M7 18.7v1.1M17 18.7v1.1M7.2 14.5h.1M16.7 14.5h.1" />
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
