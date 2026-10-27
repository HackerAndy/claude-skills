const rows = new Map();
export default { all: () => [...rows.values()], get: (id) => rows.get(id), insert: (u) => (rows.set(u.id, u), u), sessions: () => [] };
