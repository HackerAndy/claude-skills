// Target smell: Complex Method (CC 14, flat branch chain, no nesting).
export function statusLabel(code: number): string {
  if (code === 100) return "continue";
  else if (code === 200) return "ok";
  else if (code === 201) return "created";
  else if (code === 204) return "no content";
  else if (code === 301) return "moved";
  else if (code === 302) return "found";
  else if (code === 304) return "not modified";
  else if (code === 400) return "bad request";
  else if (code === 401) return "unauthorised";
  else if (code === 403) return "forbidden";
  else if (code === 404) return "not found";
  else if (code === 409) return "conflict";
  else if (code === 500) return "server error";
  return "unknown";
}
