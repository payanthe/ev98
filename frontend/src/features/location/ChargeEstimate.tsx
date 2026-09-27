import { useEffect, useId, useMemo, useState, type CSSProperties } from "react";
import type { LocationDetail, VehicleVariant } from "../../api/types";
import { formatChargerOption, formatDuration, listChargePlans } from "../../lib/chargeEstimate";
import { formatNumber, formatPower } from "../../lib/format";

const SOC_KEY = "ev98.soc";
const SOC_PRESETS = [10, 20, 50] as const;

function readSoc(): number {
  try {
    const raw = localStorage.getItem(SOC_KEY);
    if (raw == null || raw === "") return 20;
    const value = Number(raw);
    if (Number.isFinite(value) && value >= 0 && value <= 100) return Math.round(value);
  } catch {
    /* storage unavailable */
  }
  return 20;
}

function formatRate(percentPerHour: number): string {
  const rounded = percentPerHour >= 10 ? Math.round(percentPerHour) : Math.round(percentPerHour * 10) / 10;
  return formatNumber(rounded);
}

function clampSoc(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

export function ChargeEstimate({ vehicle, location }: { vehicle: VehicleVariant; location: LocationDetail }) {
  const [soc, setSoc] = useState(readSoc);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const whyId = useId();
  const sliderId = useId();
  const chargerGroupId = useId();

  useEffect(() => {
    try {
      localStorage.setItem(SOC_KEY, String(soc));
    } catch {
      /* storage unavailable */
    }
  }, [soc]);

  useEffect(() => {
    setSelectedKey(null);
    setWhyOpen(false);
  }, [location.id, vehicle.id]);

  const plans = useMemo(() => listChargePlans(vehicle, location, soc), [vehicle, location, soc]);
  const plan = plans.find((item) => item.key === selectedKey) ?? plans[0] ?? null;
  const multiCharger = plans.length > 1;

  function setFromInput(value: string) {
    const next = Number(value);
    if (!Number.isFinite(next)) return;
    setSoc(clampSoc(next));
  }

  const heroTarget = soc < 80 ? 80 : 100;
  const heroHours = plan ? (heroTarget === 80 ? plan.hoursTo80 : plan.hoursTo100) : null;
  const heroLabel = heroTarget === 80 ? "تا ۸۰٪" : "تا ۱۰۰٪";
  const secondaryHours = plan && heroTarget === 80 ? plan.hoursTo100 : null;

  const whyBits: string[] = [];
  if (plan) {
    if (plan.vehicleLimitKw != null && plan.stationKw != null && plan.vehicleLimitKw < plan.stationKw) {
      whyBits.push(`خودرو بیشتر از ${formatPower(plan.vehicleLimitKw)} قبول نمی‌کند.`);
    } else if (plan.vehicleLimitKw == null) {
      whyBits.push("محدودیت توان خودرو در داده نیست و محاسبه با توان جایگاه است.");
    }
    if (plan.batterySpread) {
      whyBits.push(`منابع چند ظرفیت داده؛ زمان با باتری ${formatNumber(plan.batteryKwh)} کیلووات‌ساعت حساب شده.`);
    }
    if (multiCharger) {
      whyBits.push("زمان برای شارژر انتخاب‌شده حساب شده؛ پیش‌فرض قوی‌ترین شارژر سازگار است.");
    }
    whyBits.push(
      plan.current === "DC"
        ? "بعد از ۸۰٪ شارژ سریع کند می‌شود و رسیدن به ۱۰۰٪ بیشتر طول می‌کشد."
        : "برای شارژ معمولی، نرخ تا انتها تقریباً ثابت فرض شده.",
    );
  }

  return (
    <section className="charge-estimate" aria-labelledby="charge-estimate-title">
      <h3 id="charge-estimate-title">زمان شارژ</h3>

      {!plan && (
        <p className="muted charge-estimate-empty">
          برای این خودرو و جایگاه توان یا ظرفیت باتری کافی ثبت نشده و زمان شارژ حساب نمی‌شود.
        </p>
      )}

      {multiCharger && (
        <div className="charge-chargers" role="group" aria-labelledby={chargerGroupId}>
          <p id={chargerGroupId} className="charge-chargers-label">
            شارژر
          </p>
          <div className="charge-chargers-list">
            {plans.map((option, index) => {
              const selected = (plan?.key ?? plans[0]?.key) === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  className={selected ? "is-on" : undefined}
                  aria-pressed={selected}
                  onClick={() => setSelectedKey(option.key)}
                >
                  <span className="charge-chargers-power">
                    {formatNumber(option.stationKw ?? option.effectiveKw)} کیلووات
                  </span>
                  <span className="charge-chargers-plug">{option.plugLabel}</span>
                  {index === 0 && <span className="charge-chargers-badge">سریع‌ترین</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {plan && (
        <div className="charge-hero" aria-live="polite">
          <p className="charge-hero-label">{heroLabel}</p>
          <p className="charge-hero-time">{formatDuration(heroHours)}</p>
          {secondaryHours != null && (
            <p className="charge-hero-secondary">
              تا ۱۰۰٪ · <strong>{formatDuration(secondaryHours)}</strong>
            </p>
          )}
          <p className="charge-hero-meta">
            {multiCharger ? formatChargerOption(plan) : `با ${plan.plugLabel}`}
            {" · "}
            توان مؤثر {formatPower(plan.effectiveKw)}
            {plan.percentPerHour >= 100
              ? ` · هر ۱۰٪ حدود ${formatDuration(10 / plan.percentPerHour)}`
              : ` · حدود ${formatRate(plan.percentPerHour)}٪ در ساعت`}
          </p>
        </div>
      )}

      <div className="charge-soc">
        <div className="charge-soc-head">
          <label htmlFor={sliderId}>شارژ فعلی</label>
          <div className="charge-soc-value">
            <input
              type="number"
              min={0}
              max={100}
              inputMode="numeric"
              value={soc}
              aria-label="درصد شارژ فعلی"
              onChange={(event) => setFromInput(event.target.value)}
            />
            <span aria-hidden="true">٪</span>
          </div>
        </div>

        <div className="charge-battery" dir="ltr" style={{ "--soc": `${soc}%` } as CSSProperties}>
          <div className="charge-battery-track" aria-hidden="true">
            <div className="charge-battery-fill" />
            <span className="charge-battery-mark charge-battery-mark-80" title="۸۰٪" />
          </div>
          <input
            id={sliderId}
            className="charge-battery-slider"
            type="range"
            min={0}
            max={100}
            step={1}
            value={soc}
            aria-valuetext={`${formatNumber(soc)} درصد`}
            onChange={(event) => setFromInput(event.target.value)}
          />
        </div>

        <div className="charge-soc-presets" role="group" aria-label="میان‌بر شارژ فعلی">
          {SOC_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              className={soc === preset ? "is-on" : undefined}
              aria-pressed={soc === preset}
              onClick={() => setSoc(preset)}
            >
              {formatNumber(preset)}٪
            </button>
          ))}
        </div>
      </div>

      {plan && whyBits.length > 0 && (
        <div className="charge-why">
          <button
            type="button"
            className="charge-why-toggle"
            aria-expanded={whyOpen}
            aria-controls={whyId}
            onClick={() => setWhyOpen((open) => !open)}
          >
            چرا این عدد؟
          </button>
          {whyOpen && (
            <ul id={whyId} className="charge-why-list">
              {whyBits.map((bit) => (
                <li key={bit}>{bit}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
