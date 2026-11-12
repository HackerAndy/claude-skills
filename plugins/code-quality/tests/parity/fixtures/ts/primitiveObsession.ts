// Target smell: Primitive Obsession and String Heavy Function Arguments.
// Fifteen functions whose arguments are all bare string / number / boolean. CodeScene needs
// about this many before the file-level percentage rule fires; five functions were not enough.

export function priceWithTax(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 1}-${strict}`;
}

export function discount(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 2}-${strict}`;
}

export function convert(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 3}-${strict}`;
}

export function roundTo(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 4}-${strict}`;
}

export function clamp(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 5}-${strict}`;
}

export function formatMoney(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 6}-${strict}`;
}

export function percent(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 7}-${strict}`;
}

export function margin(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 8}-${strict}`;
}

export function markup(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 9}-${strict}`;
}

export function splitCost(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 10}-${strict}`;
}

export function weightBand(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 11}-${strict}`;
}

export function zoneFor(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 12}-${strict}`;
}

export function etaDays(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 13}-${strict}`;
}

export function slug(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 14}-${strict}`;
}

export function initials(code: string, region: string, amount: number, strict: boolean): string {
  return `${code}-${region}-${amount * 15}-${strict}`;
}
