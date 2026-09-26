import { useEffect, useState } from "react";
import type { LocationDetail, VehicleVariant } from "../../api/types";
import { formatDuration, planCharge } from "../../lib/chargeEstimate";
import { formatNumber, formatPower } from "../../lib/format";

const SOC_KEY = "ev98.soc";

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

export function ChargeEstimate({ vehicle, location }: { vehicle: VehicleVariant; location: LocationDetail }) {
  const [soc, setSoc] = useState(readSoc);

  useEffect(() => {
    try {
      localStorage.setItem(SOC_KEY, String(soc));
    } catch {
      /* storage unavailable */
    }
  }, [soc]);

  const plan = planCharge(vehicle, location, soc);

  function setFromInput(value: string) {
    const next = Number(value);
    if (!Number.isFinite(next)) return;
    setSoc(Math.min(100, Math.max(0, Math.round(next))));
  }

  return (
    <section className="charge-estimate" aria-labelledby="charge-estimate-title">
      <h3 id="charge-estimate-title">زمان شارژ</h3>
      <label className="soc-row">
        <span>شارژ فعلی</span>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={soc}
          aria-valuetext={`${formatNumber(soc)} درصد`}
          onChange={(event) => setFromInput(event.target.value)}
        />
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
      </label>
      {!plan && (
        <p className="muted">
          برای این خودرو و جایگاه توان یا ظرفیت باتری کافی ثبت نشده و زمان شارژ حساب نمی‌شود.
        </p>
      )}
      {plan && (
        <>
          <div className="charge-stats">
            <div>
              <span>تا ۸۰٪</span>
              <strong>{formatDuration(plan.hoursTo80)}</strong>
            </div>
            <div>
              <span>تا ۱۰۰٪</span>
              <strong>{formatDuration(plan.hoursTo100)}</strong>
            </div>
          </div>
          <p>
            با {plan.plugLabel} و توان مؤثر {formatPower(plan.effectiveKw)}
            {plan.percentPerHour >= 100
              ? `، هر ۱۰ درصد حدود ${formatDuration(10 / plan.percentPerHour)} طول می‌کشد.`
              : `، هر ساعت حدود ${formatRate(plan.percentPerHour)} درصد شارژ می‌شود.`}
          </p>
          <p className="muted">
            {plan.vehicleLimitKw != null && plan.stationKw != null && plan.vehicleLimitKw < plan.stationKw
              ? `خودرو بیشتر از ${formatPower(plan.vehicleLimitKw)} قبول نمی‌کند. `
              : plan.vehicleLimitKw == null
                ? "محدودیت توان خودرو در داده نیست و محاسبه با توان جایگاه است. "
                : ""}
            {plan.batterySpread
              ? `منبع چند ظرفیت داده؛ زمان با باتری ${formatNumber(plan.batteryKwh)} کیلووات‌ساعت حساب شده. `
              : ""}
            {plan.current === "DC"
              ? "بعد از ۸۰٪ شارژ سریع کند می‌شود و رسیدن به ۱۰۰٪ بیشتر طول می‌کشد."
              : "برای شارژ معمولی، نرخ تا انتها تقریباً ثابت فرض شده."}
          </p>
        </>
      )}
    </section>
  );
}
