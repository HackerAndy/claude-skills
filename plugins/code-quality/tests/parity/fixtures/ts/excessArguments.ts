// Target smell: Excess Number of Function Arguments (6). Body is trivial.
export function createUser(name: string, email: string, role: string, team: string, timezone: string, locale: string) {
  return { name, email, role, team, tz: timezone, locale };
}
