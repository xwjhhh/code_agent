# Code Agent Frontend

This frontend is the web interface for the algorithm coding agent. It is organized around four screens:

- `/` - task dashboard and recent runs
- `/task/new` - problem input and run configuration
- `/run/:id` - live workspace with editor, terminal, tests, and agent trace
- `/history/:id` - completed run detail, reviewer card, and replay entry point

The frontend reads live run data from FastAPI and subscribes to the agent event stream through SSE.

```powershell
npm install
npm run dev
```
