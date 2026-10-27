import { Router } from 'express';
import * as users from '../services/userService.js';
import db from '../repositories/userRepo.js'; // shortcut to the DB layer
const router = Router();
router.get('/', async (req, res) => res.json(await users.list()));
router.get('/:id', async (req, res) => res.json(await users.get(req.params.id)));
router.post('/', async (req, res) => res.status(201).json(await users.create(req.body)));
router.get('/:id/sessions', async (req, res) => res.json(db.sessions(req.params.id))); // not in contract
export default router;
