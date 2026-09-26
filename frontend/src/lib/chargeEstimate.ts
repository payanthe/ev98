import type { LocationDetail, VehicleVariant } from "../api/types";
import { formatNumber } from "./format";

const DC_STANDARDS = new Set(["CCS_1", "CCS_2", "GBT_DC", "CHADEMO", "NACS", "TESLA"]);
const AC_STANDARDS = new Set(["TYPE_1", "TYPE_2", "GBT_AC", "SCHUKO", "TYPE_3"]);

/** Extra time for conversion loss. AC is higher because the onboard charger is less efficient. */
const AC_LOSS = 1.15;
const DC_LOSS = 1.08;
/** Average power from 80% to 100% on DC, as a share of the peak the car is taking. */
const DC_TAPER = 0.35;

export type ChargeCurrent = "AC" | "DC";

export type ChargePlan = {
  plugLabel: string;
  current: ChargeCurrent;
  effectiveKw: number;
  stationKw: number | null;
  vehicleLimitKw: number | null;
  batteryKwh: number;
  batterySpread: boolean;
  percentPerHour: number;
  hoursTo80: number | null;
  hoursTo100: number | null;
};

function currentOf(standard: string, powerType: string | null): ChargeCurrent | null {
  if (DC_STANDARDS.has(standard)) return "DC";
  if (AC_STANDARDS.has(standard)) return "AC";
  const text = (powerType || "").toUpperCase();
  if (text.startsWith("DC")) return "DC";
  if (text.startsWith("AC")) return "AC";
  return null;
}

function positive(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

function batteryOf(vehicle: VehicleVariant): { kwh: number; spread: boolean } | null {
  const min = positive(vehicle.battery_kwh_min);
  const max = positive(vehicle.battery_kwh_max);
  if (min == null && max == null) return null;
  if (min != null && max != null && min !== max) return { kwh: max, spread: true };
  return { kwh: (max ?? min) as number, spread: false };
}

function hoursForShare(share: number, batteryKwh: number, kw: number, loss: number): number {
  if (share <= 0 || kw <= 0) return 0;
  return (batteryKwh * share * loss) / kw;
}

function hoursBetween(soc: number, target: number, batteryKwh: number, kw: number, current: ChargeCurrent): number {
  if (soc >= target) return 0;
  const loss = current === "AC" ? AC_LOSS : DC_LOSS;
  if (current === "AC") return hoursForShare((target - soc) / 100, batteryKwh, kw, loss);
  let hours = 0;
  if (soc < 80 && target > soc) {
    const upper = Math.min(target, 80);
    hours += hoursForShare((upper - soc) / 100, batteryKwh, kw, loss);
  }
  if (target > 80 && soc < target) {
    const lower = Math.max(soc, 80);
    hours += hoursForShare((target - lower) / 100, batteryKwh, kw * DC_TAPER, loss);
  }
  return hours;
}

export function planCharge(vehicle: VehicleVariant, location: LocationDetail, socPercent: number): ChargePlan | null {
  const battery = batteryOf(vehicle);
  if (!battery) return null;
  const allowed = new Set(vehicle.station_standards);
  const soc = Math.min(100, Math.max(0, socPercent));

  let best: ChargePlan | null = null;
  for (const evse of location.evses) {
    for (const connector of evse.connectors) {
      if (!allowed.has(connector.standard)) continue;
      const current = currentOf(connector.standard, connector.power_type);
      if (!current) continue;
      const sameFamily = evse.connectors.every(
        (item) => currentOf(item.standard, item.power_type) === current,
      );
      const stationKw = positive(connector.max_power_kw) ?? (sameFamily ? positive(evse.max_power_kw) : null);
      const vehicleLimitKw = positive(current === "DC" ? vehicle.dc_charge_limit_kw : vehicle.ac_charge_limit_kw);
      const known = [stationKw, vehicleLimitKw].filter((value): value is number => value != null);
      if (known.length === 0) continue;
      const effectiveKw = Math.min(...known);
      const loss = current === "AC" ? AC_LOSS : DC_LOSS;
      const windowKw = current === "DC" && soc >= 80 ? effectiveKw * DC_TAPER : effectiveKw;
      const plan: ChargePlan = {
        plugLabel: connector.standard_label,
        current,
        effectiveKw,
        stationKw,
        vehicleLimitKw,
        batteryKwh: battery.kwh,
        batterySpread: battery.spread,
        percentPerHour: (windowKw / loss / battery.kwh) * 100,
        hoursTo80: soc >= 80 ? null : hoursBetween(soc, 80, battery.kwh, effectiveKw, current),
        hoursTo100: soc >= 100 ? null : hoursBetween(soc, 100, battery.kwh, effectiveKw, current),
      };
      if (
        !best ||
        plan.effectiveKw > best.effectiveKw ||
        (plan.effectiveKw === best.effectiveKw && plan.current === "DC" && best.current === "AC")
      ) {
        best = plan;
      }
    }
  }
  return best;
}

export function formatDuration(hours: number | null): string {
  if (hours == null) return "رسیده";
  if (hours <= 0) return "رسیده";
  const minutes = Math.max(1, Math.round(hours * 60));
  if (minutes < 60) return `${formatNumber(minutes)} دقیقه`;
  const whole = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (rest < 5) return `${formatNumber(whole)} ساعت`;
  return `${formatNumber(whole)} ساعت و ${formatNumber(rest)} دقیقه`;
}
