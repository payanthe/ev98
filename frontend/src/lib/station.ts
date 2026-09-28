const STATION_PATH = /^\/stations\/([^/]+)\/?$/;
const SLUG = /^[\u0600-\u06FFa-z0-9]+(?:-[\u0600-\u06FFa-z0-9]+)*$/;

export function stationSlugFromPath(pathname: string): string | null {
  const match = STATION_PATH.exec(pathname);
  if (!match) return null;
  try {
    const slug = decodeURIComponent(match[1]);
    return SLUG.test(slug) ? slug : null;
  } catch {
    return null;
  }
}

export function stationHref(slug: string): string {
  return `/stations/${encodeURIComponent(slug)}`;
}
