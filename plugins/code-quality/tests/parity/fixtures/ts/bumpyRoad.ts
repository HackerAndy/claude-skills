// Target smell: Bumpy Road (3 bumps, each nested 2 deep). Nesting and CC stay low.
interface Contact { name?: string; email?: string; phone?: string; seen?: boolean; checked?: boolean }

export function normalise(record: Contact): Contact {
  if (record.name) {
    if (record.name === record.name.toUpperCase()) {
      record.name = record.name.toLowerCase();
    }
  }
  record.seen = true;
  if (record.email) {
    if (record.email.includes(" ")) {
      record.email = record.email.trim();
    }
  }
  record.checked = true;
  if (record.phone) {
    if (record.phone.startsWith("00")) {
      record.phone = "+" + record.phone.slice(2);
    }
  }
  return record;
}
