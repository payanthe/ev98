import { useEffect, useRef, useState, type ReactNode } from "react";
import type { LocationFilters, VehicleVariant } from "../../api/types";
import { VehiclePicker } from "../vehicles/VehiclePicker";
import { CONNECTOR_FILTERS, EMPTY_FILTERS, POWER_FILTERS, activeFilterCount, filterSummary } from "../../lib/filters";
import { findVehicle, useVehicleCatalog } from "../../lib/vehicles";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { formatNumber } from "../../lib/format";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconCheck, IconFilter, IconPowerLevel } from "../../ui/icons";

export function FilterBar({
  filters,
  detailOpen,
  nearbyOpen = false,
  onChange,
  children,
}: {
  filters: LocationFilters;
  detailOpen: boolean;
  nearbyOpen?: boolean;
  onChange: (filters: LocationFilters) => void;
  children?: ReactNode;
}) {
  const isMobile = useMediaQuery("(max-width: 800px)");
  const desktopDetail = detailOpen && !isMobile;
  const desktopNearby = nearbyOpen && !detailOpen && !isMobile;
  const panelOpen = detailOpen || nearbyOpen;
  const [open, setOpen] = useState(() => !isMobile);
  const [vehicleStep, setVehicleStep] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const vehicles = useVehicleCatalog();
  const selected = findVehicle(vehicles.data, filters.vehicleId);
  const vehicle: VehicleVariant | null = selected?.variant ?? null;
  const expanded = open;
  const count = activeFilterCount(filters);
  const summary = filterSummary(filters, vehicle?.display_name);
  const showToggle = isMobile || detailOpen || nearbyOpen || vehicleStep;
  const showHeadClear = !vehicleStep && count > 0 && !desktopDetail;
  const showSummary = !expanded && Boolean(summary) && !desktopDetail;
  const showStatus = !vehicleStep && !desktopDetail;

  useEffect(() => {
    if (panelOpen) {
      setOpen(false);
      setVehicleStep(false);
    } else if (!isMobile) {
      setOpen(true);
    }
  }, [panelOpen, isMobile]);

  useEffect(() => {
    const dismissOnOutside = (desktopDetail || desktopNearby) && open;
    if (!vehicleStep && !dismissOnOutside) return;
    function onPointerDown(event: PointerEvent) {
      if (!dismissOnOutside) return;
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
      setVehicleStep(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (vehicleStep) {
        setVehicleStep(false);
        return;
      }
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [desktopDetail, desktopNearby, open, vehicleStep]);

  function connectorIsOn(id: string) {
    if (!vehicle) return filters.connectors.includes(id);
    if (filters.connectors.length === 0) return vehicle.station_standards.includes(id);
    return filters.connectors.includes(id);
  }

  function toggleConnector(id: string) {
    if (vehicle && !vehicle.station_standards.includes(id)) return;
    const base = vehicle && filters.connectors.length === 0 ? [...vehicle.station_standards] : filters.connectors;
    const next = base.includes(id) ? base.filter((item) => item !== id) : [...base, id];
    if (next.length === 0) return;
    const coversVehicle =
      vehicle != null &&
      vehicle.station_standards.length === next.length &&
      vehicle.station_standards.every((item) => next.includes(item));
    onChange({ ...filters, connectors: coversVehicle ? [] : next });
  }

  return (
    <div
      ref={rootRef}
      className={`filters${expanded ? " is-expanded" : " is-compact"}${vehicleStep ? " is-vehicle-step" : ""}${desktopDetail ? " is-detail-dock" : ""}${desktopNearby ? " is-nearby-dock" : ""}`}
    >
      {showToggle && (
        <div className="filters-head">
          {vehicleStep ? (
            <button type="button" className="filters-back" onClick={() => setVehicleStep(false)}>
              <IconFilter />
              بازگشت به فیلترها
            </button>
          ) : (
            <button
              type="button"
              className={`filters-toggle${desktopDetail && !open ? " is-chip" : ""}`}
              aria-expanded={open}
              aria-controls="map-filters"
              aria-label={open ? "جمع کردن فیلترها" : count > 0 ? `فیلترها، ${formatNumber(count)} مورد فعال` : "فیلترها"}
              onClick={() => setOpen((current) => {
                if (current) setVehicleStep(false);
                return !current;
              })}
            >
              <IconFilter />
              {desktopDetail && !open ? null : open ? "جمع کردن فیلترها" : "فیلترها"}
              {count > 0 && <span className="count-badge">{formatNumber(count)}</span>}
            </button>
          )}
          {showHeadClear && (
            <button type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              پاک کردن
            </button>
          )}
        </div>
      )}
      {showSummary && <p className="filter-summary">{summary}</p>}
      {expanded && (
        <div className="filters-body" id="map-filters">
          {vehicleStep ? (
            <VehiclePicker
              key="vehicle-inline-step"
              inline
              catalog={vehicles.data}
              loading={vehicles.isLoading}
              error={vehicles.isError}
              vehicleId={filters.vehicleId}
              onRetry={() => void vehicles.refetch()}
              onCancel={() => setVehicleStep(false)}
              onSelect={(variant) => {
                onChange({ ...filters, vehicleId: variant.id, connectors: [] });
                setVehicleStep(false);
              }}
              onClear={() => onChange({ ...filters, vehicleId: null, connectors: [] })}
            />
          ) : <>
          <VehiclePicker
            key="vehicle-filter-trigger"
            catalog={vehicles.data}
            loading={vehicles.isLoading}
            error={vehicles.isError}
            vehicleId={filters.vehicleId}
            onRetry={() => void vehicles.refetch()}
            onOpenRequest={() => {
              setOpen(true);
              setVehicleStep(true);
            }}
            onSelect={(variant) => onChange({ ...filters, vehicleId: variant.id, connectors: [] })}
            onClear={() => onChange({ ...filters, vehicleId: null, connectors: [] })}
          />
          <div className="filter-group connector-filter-group" role="group" aria-labelledby="filter-connectors">
            <span className="group-label" id="filter-connectors">
              کانکتور
            </span>
            {CONNECTOR_FILTERS.map((connector) => {
              const blocked = vehicle != null && !vehicle.station_standards.includes(connector.id);
              const pressed = connectorIsOn(connector.id);
              return (
                <button
                  key={connector.id}
                  type="button"
                  aria-pressed={pressed}
                  aria-disabled={blocked}
                  disabled={blocked}
                  title={blocked ? "این درگاه با خودروی انتخاب‌شده سازگار نیست" : undefined}
                  className={pressed ? "is-on" : ""}
                  onClick={() => toggleConnector(connector.id)}
                >
                  <ConnectorMark standard={connector.id} />
                  {connector.label}
                  {pressed && <IconCheck />}
                </button>
              );
            })}
          </div>
          <div className="filter-group power-filter-group" role="group" aria-labelledby="filter-power">
            <span className="group-label" id="filter-power">
              حداقل توان شارژر
            </span>
            {POWER_FILTERS.map((power) => {
              const pressed = filters.minPowerKw === power.value;
              return (
                <button
                  key={power.value}
                  type="button"
                  aria-pressed={pressed}
                  aria-label={`${power.label}، حداقل ${power.summary}`}
                  className={`power-filter power-filter-${power.level}${pressed ? " is-on" : ""}`}
                  onClick={() => onChange({ ...filters, minPowerKw: pressed ? null : power.value })}
                >
                  <span className="power-filter-icon">
                    <IconPowerLevel level={power.level} />
                  </span>
                  <span className="power-filter-copy">
                    <strong>{power.label}</strong>
                    <small dir="ltr">{power.summary}</small>
                  </span>
                  {pressed && <span className="power-filter-check"><IconCheck /></span>}
                </button>
              );
            })}
          </div>
          {/* Phase 1: فیلتر وضعیت (فقط آزاد) مخفی — در فاز اول فقط محل ایستگاه‌ها؛ وضعیت زنده بعداً */}
          {/*
          <div className="filter-group" role="group" aria-labelledby="filter-status">
            <span className="group-label" id="filter-status">
              وضعیت
            </span>
            <button
              type="button"
              aria-pressed={filters.availability === "available"}
              className={filters.availability === "available" ? "is-on" : ""}
              onClick={() =>
                onChange({
                  ...filters,
                  availability: filters.availability === "available" ? null : "available",
                })
              }
            >
              {filters.availability === "available" && <IconCheck />}
              فقط آزاد
            </button>
          </div>
          */}
          {/* Phase 1: فیلتر منبع (شارینت) مخفی — منابع به کاربر نشان داده نمی‌شود */}
          {/*
          <div className="filter-group" role="group" aria-labelledby="filter-source">
            <span className="group-label" id="filter-source">
              منبع
            </span>
            <button
              type="button"
              aria-pressed={filters.source === "sharinet"}
              className={filters.source === "sharinet" ? "is-on" : ""}
              onClick={() =>
                onChange({ ...filters, source: filters.source === "sharinet" ? null : "sharinet" })
              }
            >
              {filters.source === "sharinet" && <IconCheck />}
              شارینت
            </button>
          </div>
          */}
          {(!isMobile || desktopDetail) && count > 0 && (
            <button type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              پاک کردن
            </button>
          )}
          </>}
        </div>
      )}
      {showStatus && children}
    </div>
  );
}
