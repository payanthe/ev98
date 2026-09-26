import { useEffect, useState, type ReactNode } from "react";
import type { LocationFilters, VehicleVariant } from "../../api/types";
import { VehiclePicker } from "../vehicles/VehiclePicker";
import { CONNECTOR_FILTERS, EMPTY_FILTERS, POWER_FILTERS, activeFilterCount, filterSummary } from "../../lib/filters";
import { findVehicle, useVehicleCatalog } from "../../lib/vehicles";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { formatNumber } from "../../lib/format";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconCheck, IconPowerLevel } from "../../ui/icons";

export function FilterBar({
  filters,
  detailOpen,
  onChange,
  children,
}: {
  filters: LocationFilters;
  detailOpen: boolean;
  onChange: (filters: LocationFilters) => void;
  children?: ReactNode;
}) {
  const isMobile = useMediaQuery("(max-width: 800px)");
  const [open, setOpen] = useState(false);
  const vehicles = useVehicleCatalog();
  const selected = findVehicle(vehicles.data, filters.vehicleId);
  const vehicle: VehicleVariant | null = selected?.variant ?? null;
  const expanded = !isMobile || open;
  const count = activeFilterCount(filters);
  const summary = filterSummary(filters, vehicle?.display_name);

  useEffect(() => {
    if (detailOpen && isMobile) setOpen(false);
  }, [detailOpen, isMobile]);

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
    <div className="filters">
      <VehiclePicker
        catalog={vehicles.data}
        loading={vehicles.isLoading}
        error={vehicles.isError}
        vehicleId={filters.vehicleId}
        onRetry={() => void vehicles.refetch()}
        onSelect={(variant) => onChange({ ...filters, vehicleId: variant.id, connectors: [] })}
        onClear={() => onChange({ ...filters, vehicleId: null, connectors: [] })}
      />
      {isMobile && (
        <div className="filters-head">
          <button
            type="button"
            className="filters-toggle"
            aria-expanded={open}
            aria-controls="map-filters"
            onClick={() => setOpen((current) => !current)}
          >
            فیلترها
            {count > 0 && <span className="count-badge">{formatNumber(count)}</span>}
          </button>
          {count > 0 && (
            <button type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              پاک کردن
            </button>
          )}
        </div>
      )}
      {isMobile && !open && summary && <p className="filter-summary">{summary}</p>}
      {expanded && (
        <div className="filters-body" id="map-filters">
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
          {!isMobile && count > 0 && (
            <button type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              پاک کردن
            </button>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
