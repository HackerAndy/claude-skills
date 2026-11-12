// Target smell: Complex Conditional (one condition with 4 clauses). Nothing else.
interface Order { paid: boolean; address: string; onHold: boolean; override: boolean }

export function canShip(order: Order): boolean {
  if ((order.paid && order.address && !order.onHold) || order.override) {
    return true;
  }
  return false;
}
