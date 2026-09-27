import chademo from "../assets/connectors/Chademo_type4.svg";
import tesla from "../assets/connectors/Tesla-hpwc-model-s.svg";
import ccs1 from "../assets/connectors/Type1_CCS.svg";
import type1 from "../assets/connectors/Type1_J1772.svg";
import ccs2 from "../assets/connectors/Type2_CCS.svg";
import type2 from "../assets/connectors/Type2_socket.svg";
import type2Cable from "../assets/connectors/Type2_tethered.svg";
import type3 from "../assets/connectors/Type3c.svg";
import unknown from "../assets/connectors/Unknown.svg";
import schuko from "../assets/connectors/schuko.svg";
import gbtAc from "../assets/connectors/Gbt_ac.svg";
import gbtDc from "../assets/connectors/Gbt_dc.svg";

const ICONS: Record<string, string> = {
  CCS_1: ccs1,
  CCS_2: ccs2,
  TYPE_1: type1,
  TYPE_2: type2,
  CHADEMO: chademo,
  SCHUKO: schuko,
  TESLA: tesla,
  TYPE_3: type3,
  UNKNOWN: unknown,
  GBT_AC: gbtAc,
  GBT_DC: gbtDc,
};

export function connectorIcon(standard: string, format?: string | null): string | null {
  if (standard === "TYPE_2" && format?.toUpperCase() === "CABLE") return type2Cable;
  return ICONS[standard] ?? null;
}

export function ConnectorMark({
  standard,
  format,
  label,
  labelled = false,
}: {
  standard: string;
  format?: string | null;
  label?: string;
  labelled?: boolean;
}) {
  const src = connectorIcon(standard, format);
  if (!src) return null;
  return <img className="connector-icon" src={src} alt={labelled ? label || "" : ""} aria-hidden={labelled ? undefined : true} />;
}
