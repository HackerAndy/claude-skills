import repo from '../repositories/userRepo.js';
import { UserSchema } from '../schemas/user.js';
export const list = () => repo.all();
export const get = (id) => repo.get(id);
export const create = (body) => repo.insert(UserSchema.parse(body));
