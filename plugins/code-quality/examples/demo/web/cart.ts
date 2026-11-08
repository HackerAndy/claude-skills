export interface Item { price: number; qty: number }

export function cartTotal(items: Item[]): number {
  return items.reduce((sum, i) => sum + i.price * i.qty, 0)
}
