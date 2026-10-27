import express from 'express';
import usersRouter from './routes/users.js';
const app = express();
app.use(express.json());
app.use('/api/users', usersRouter);
app.get('/health', (req, res) => res.json({ status: 'ok' }));
export default app;
