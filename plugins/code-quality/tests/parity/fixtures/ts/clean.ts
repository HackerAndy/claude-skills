// Control: small, flat, well-factored code. Expect no findings and a score of 10.
interface Item { price: number }

const RATES: Record<string, number> = { EU: 1.07, US: 1.0 };
const DEFAULT_RATE = 1.1;

export function linePrice(item: Item, region: string): number {
  return item.price * (RATES[region] ?? DEFAULT_RATE);
}

export function orderTotal(items: Item[], region: string): number {
  return items.reduce((sum, item) => sum + linePrice(item, region), 0);
}
