// Target smell: Nested Complexity (depth 4). Cyclomatic complexity stays under 9.
interface Invoice { id: string; due: number; paid: boolean }
interface Account { active: boolean; invoices: Invoice[] }

export function findOverdue(accounts: Account[], today: number): string[] {
  const overdue: string[] = [];
  for (const account of accounts) {
    if (account.active) {
      for (const invoice of account.invoices) {
        if (invoice.due < today) {
          if (!invoice.paid) {
            overdue.push(invoice.id);
          }
        }
      }
    }
  }
  return overdue;
}
