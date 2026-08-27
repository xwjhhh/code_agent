# Code Agent Frontend

This is the first UI prototype for the algorithm coding agent. It is organized around four screens:

- `/` - task dashboard and recent runs
- `/task/new` - problem input and run configuration
- `/run/:id` - live workspace with editor, terminal, tests, and agent trace
- `/history/:id` - completed run detail, reviewer card, and replay entry point

The prototype uses local data in `lib/data.ts` so the interaction and visual hierarchy can be reviewed before the FastAPI transport is connected. Replace those data reads with an SSE or WebSocket client when the backend event stream is ready.

```powershell
npm install
npm run dev
```
