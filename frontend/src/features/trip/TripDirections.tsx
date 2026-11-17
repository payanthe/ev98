import type { TripDirection } from "../../api/types";

const turns: Record<string, string> = {
  "slight left": "کمی به چپ برو",
  left: "به چپ بپیچ",
  "sharp left": "پیچ تند به چپ را طی کن",
  "slight right": "کمی به راست برو",
  right: "به راست بپیچ",
  "sharp right": "پیچ تند به راست را طی کن",
  uturn: "دور بزن",
  straight: "مستقیم ادامه بده",
};

function instruction(step: TripDirection, last: boolean) {
  const side = step.modifier?.includes("left") ? "چپ" : "راست";
  switch (step.type) {
    case "depart": return "حرکت کن";
    case "arrive": return last ? "به مقصد رسیدی" : "به نقطهٔ توقف رسیدی";
    case "roundabout":
    case "rotary":
    case "roundabout turn":
      return step.exit ? `از خروجی ${step.exit.toLocaleString("fa-IR")} میدان خارج شو` : "وارد میدان شو";
    case "exit roundabout":
    case "exit rotary": return "از میدان خارج شو";
    case "off ramp": return `از خروجی ${side} خارج شو`;
    case "fork": return `از شاخهٔ ${side} برو`;
    case "merge": return "به مسیر اصلی بپیوند";
    default: return turns[step.modifier ?? "straight"] ?? "ادامه بده";
  }
}

export function TripDirections({ steps }: { steps: TripDirection[] }) {
  if (!steps.length) return null;
  return (
    <details className="trip-directions">
      <summary>راهنمای مسیر رانندگی</summary>
      <ol>
        {steps.map((step, index) => (
          <li key={index}>
            <span>{instruction(step, index === steps.length - 1)}{step.road ? ` · ${step.road}` : ""}</span>
            {step.distance_m > 0 && <small>{step.distance_m.toLocaleString("fa-IR")} متر تا مرحلهٔ بعد</small>}
          </li>
        ))}
      </ol>
    </details>
  );
}
