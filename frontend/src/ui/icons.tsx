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
