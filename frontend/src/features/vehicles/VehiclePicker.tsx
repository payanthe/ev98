import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import type { VehicleCatalog, VehicleVariant } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { findVehicle, sortMakesForDisplay, variantMatches } from "../../lib/vehicles";
import { BrandMark } from "../../ui/BrandMark";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconBattery, IconBolt, IconCar, IconCheck, IconClose, IconPlug, IconRange, IconSearch } from "../../ui/icons";

function batteryLabel(variant: VehicleVariant): string | null {
  if (variant.battery_kwh_min == null) return null;
  const max = variant.battery_kwh_max;
  const text =
    max != null && max !== variant.battery_kwh_min
      ? `${formatNumber(variant.battery_kwh_min)}–${formatNumber(max)}`
      : formatNumber(variant.battery_kwh_min);
  return `${text} kWh`;
}

function VehicleSpec({
  icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "power" | "battery" | "range";
}) {
  return (
    <div className={`vehicle-spec vehicle-spec-${tone}`}>
      <span className="vehicle-spec-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="vehicle-spec-copy">
        <span className="vehicle-spec-label">{label}</span>
        <strong className="vehicle-spec-value">{value}</strong>
        {hint && <span className="vehicle-spec-hint">{hint}</span>}
      </span>
    </div>
  );
}

function VehicleFacts({ variant }: { variant: VehicleVariant }) {
  const battery = batteryLabel(variant);
  const connectors = variant.connectors;
  const hasChargeLimits = variant.ac_charge_limit_kw != null || variant.dc_charge_limit_kw != null;

  return (
    <div className="vehicle-specs">
      <div className="vehicle-spec-grid">
        <VehicleSpec
          tone="power"
          icon={<IconBolt />}
          label="پیشرانه"
          value={variant.powertrain_label}
        />
        {battery && (
          <VehicleSpec
            tone="battery"
            icon={<IconBattery />}
            label="باتری"
            value={<bdi>{battery}</bdi>}
          />
        )}
        {variant.range_km != null && (
          <VehicleSpec
            tone="range"
            icon={<IconRange />}
            label="برد"
            value={<bdi>{formatNumber(variant.range_km)} km</bdi>}
            hint={variant.range_standard ? <bdi dir="ltr">{variant.range_standard}</bdi> : undefined}
          />
        )}
        {hasChargeLimits && (
          <VehicleSpec
            tone="neutral"
            icon={<IconPlug />}
            label="حد شارژ"
            value={
              <span className="vehicle-charge-limits" dir="ltr">
                {variant.ac_charge_limit_kw != null && <span>AC {formatNumber(variant.ac_charge_limit_kw)} kW</span>}
                {variant.ac_charge_limit_kw != null && variant.dc_charge_limit_kw != null && <span aria-hidden="true">·</span>}
                {variant.dc_charge_limit_kw != null && <span>DC {formatNumber(variant.dc_charge_limit_kw)} kW</span>}
              </span>
            }
          />
        )}
      </div>

      {connectors.length > 0 && (
        <div className="vehicle-ports">
          <div className="vehicle-ports-head">
            <IconPlug />
            <span>درگاه‌های شارژ</span>
          </div>
          <ul className="vehicle-ports-list">
            {connectors.map((connector) => (
              <li key={connector.code} className={`vehicle-port is-${connector.current_type.toLowerCase()}`}>
                <span className="vehicle-port-mark">
                  <ConnectorMark standard={connector.station_standard} label={connector.display_name} />
                </span>
                <span className="vehicle-port-copy">
                  <strong dir="ltr">{connector.display_name}</strong>
                  <span className="vehicle-port-type">{connector.current_type === "DC" ? "شارژ سریع DC" : "شارژ AC"}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function VehiclePicker({
  catalog,
  loading,
  error,
  vehicleId,
  onSelect,
  onClear,
  onRetry,
  inline = false,
  onOpenRequest,
  onCancel,
}: {
  catalog: VehicleCatalog | undefined;
  loading: boolean;
  error: boolean;
  vehicleId: string | null;
  onSelect: (variant: VehicleVariant) => void;
  onClear: () => void;
  onRetry: () => void;
  inline?: boolean;
  onOpenRequest?: () => void;
  onCancel?: () => void;
}) {
  const listId = useId();
  const dialogId = useId();
  const titleId = useId();
  const searchId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(inline);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const selected = findVehicle(catalog, vehicleId);

  const groups = useMemo(() => {
    if (!catalog) return [];
    return sortMakesForDisplay(catalog.makes)
      .map((make) => ({
        make,
        variants: make.models.flatMap((model) => model.variants).filter((variant) => variantMatches(variant.search, query)),
      }))
      .filter((group) => group.variants.length > 0);
  }, [catalog, query]);

  const flat = useMemo(() => groups.flatMap((group) => group.variants.map((variant) => ({ make: group.make, variant }))), [groups]);
  const variantIndexes = useMemo(
    () => new Map(flat.map((item, index) => [item.variant.id, index])),
    [flat],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    if (inline) setOpen(true);
  }, [inline]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    if (inline) return;
    document.documentElement.classList.add("has-vehicle-picker");
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.documentElement.classList.remove("has-vehicle-picker");
    };
  }, [inline, open]);

  useEffect(() => {
    if (!open) return;
    const active = flat[activeIndex];
    if (!active) return;
    document.getElementById(`${listId}-${active.variant.id}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, flat, listId, open]);

  function close(focusTrigger = true) {
    setOpen(false);
    setQuery("");
    if (inline) {
      onCancel?.();
      return;
    }
    if (focusTrigger) triggerRef.current?.focus();
  }

  function choose(variant: VehicleVariant) {
    onSelect(variant);
    close();
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "ArrowDown" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % flat.length);
    } else if (event.key === "ArrowUp" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + flat.length) % flat.length);
    } else if (event.key === "Home" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex(flat.length - 1);
    } else if (event.key === "Enter") {
      const item = flat[activeIndex] ?? flat[0];
      if (item) {
        event.preventDefault();
        choose(item.variant);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }

  const activeId = open && flat[activeIndex] ? `${listId}-${flat[activeIndex].variant.id}` : undefined;

  return (
    <div className={`vehicle-picker${inline ? " is-inline" : ""}`} ref={rootRef}>
      {!inline && (
        <div className={`vehicle-slot${selected ? " has-selection" : ""}`}>
          <button
            type="button"
            ref={triggerRef}
            className={selected ? "vehicle-trigger is-on" : "vehicle-trigger"}
            aria-expanded={open}
            aria-controls={open ? dialogId : undefined}
            aria-haspopup="dialog"
            onClick={() => (open ? close(false) : onOpenRequest ? onOpenRequest() : setOpen(true))}
          >
            {selected ? (
              <>
                <BrandMark icon={selected.make.icon} name={selected.make.name_en} />
                <span className="vehicle-trigger-copy">
                  <span className="vehicle-kicker">خودروی من</span>
                  <span className="vehicle-name" dir="ltr">{selected.make.name_en} {selected.variant.model_name}</span>
                </span>
              </>
            ) : (
              <>
                <IconCar />
                <span className="vehicle-trigger-copy">
                  <span className="vehicle-name">انتخاب خودروی من</span>
                  <span className="vehicle-kicker">نمایش جایگاه‌های سازگار</span>
                </span>
              </>
            )}
          </button>
          {selected && (
            <button type="button" className="vehicle-remove" onClick={onClear}>
              حذف خودرو
            </button>
          )}
        </div>
      )}
      {open && (
        <>
          {!inline && <div className="vehicle-scrim" aria-hidden="true" onPointerDown={() => close()} />}
          <div className="vehicle-panel" id={dialogId} role={inline ? "region" : "dialog"} aria-modal={inline ? undefined : true} aria-labelledby={titleId}>
            <header className="vehicle-panel-head">
              <div>
                <h2 id={titleId}>خودروی شما چیست؟</h2>
                <p>تا فقط شارژرهایی را ببینید که به خودروی شما می‌خورند.</p>
              </div>
              <button
                type="button"
                className="vehicle-panel-close"
                aria-label={inline ? "انصراف و بازگشت به فیلترها" : "بستن"}
                onClick={() => close()}
              >
                {inline ? "انصراف" : <IconClose />}
              </button>
            </header>
            <label className="vehicle-search-label" htmlFor={searchId}>جست‌وجوی برند یا مدل</label>
            <div className="vehicle-search">
              <IconSearch />
              <input
                id={searchId}
                ref={inputRef}
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={flat.length > 0}
                aria-controls={flat.length > 0 ? listId : undefined}
                aria-activedescendant={activeId}
                placeholder="مثلاً BYD یا E30X"
                value={query}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={onKeyDown}
              />
              {query && (
                <button type="button" className="vehicle-clear" aria-label="پاک کردن جست‌وجو" onClick={() => setQuery("")}>
                  <IconClose />
                </button>
              )}
            </div>
            {!loading && !error && (
              <p className="vehicle-results" aria-live="polite">
                {query
                  ? `${formatNumber(flat.length)} خودرو پیدا شد`
                  : `${formatNumber(flat.length)} خودرو از ${formatNumber(groups.length)} برند`}
              </p>
            )}
            <div className="vehicle-list">
            {loading && <p>در حال خواندن فهرست خودروها…</p>}
            {error && (
              <p role="alert">
                فهرست خودروها دریافت نشد.
                <button type="button" onClick={onRetry}>
                  دوباره
                </button>
              </p>
            )}
            {!loading && !error && flat.length === 0 && <p>خودرویی با این نام پیدا نشد.</p>}
            {flat.length > 0 && (
              <ul id={listId} role="listbox" aria-label="خودروها">
                {groups.map((group) => (
                  <li key={group.make.slug}>
                    <p className="vehicle-make">
                      <BrandMark icon={group.make.icon} name={group.make.name_en} />
                      <span className="vehicle-make-names">
                        <b dir="ltr">{group.make.name_en}</b>
                        <span>{group.make.name_fa}</span>
                      </span>
                      <span className="vehicle-make-count">{formatNumber(group.variants.length)} مدل</span>
                    </p>
                    <ul>
                      {group.variants.map((variant) => {
                        const index = variantIndexes.get(variant.id) ?? 0;
                        const active = index === activeIndex;
                        const current = selected?.variant.id === variant.id;
                        return (
                          <li
                            key={variant.id}
                            id={`${listId}-${variant.id}`}
                            role="option"
                            aria-selected={current}
                            className={[active ? "is-active" : "", current ? "is-current" : ""]
                              .filter(Boolean)
                              .join(" ")}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={() => choose(variant)}
                          >
                            <span className="vehicle-option-title">
                              <b>
                                {variant.model_name}
                                {variant.model_year && <bdi className="vehicle-year">{variant.model_year}</bdi>}
                              </b>
                              {current && <span className="vehicle-current"><IconCheck /> انتخاب‌شده</span>}
                            </span>
                            <VehicleFacts variant={variant} />
                            {variant.importer_name_fa && (
                              <span className="vehicle-importer">
                                <span>واردکننده</span>
                                <b>{variant.importer_name_fa}</b>
                              </span>
                            )}
                            {variant.warnings[0] && <span className="vehicle-warning">{variant.warnings[0]}</span>}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
            </div>
            <p className="vehicle-note">
              با انتخاب خودرو، فیلتر کانکتورها خودکار تنظیم می‌شود. هر زمان بخواهید می‌توانید خودرو را تغییر دهید.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
