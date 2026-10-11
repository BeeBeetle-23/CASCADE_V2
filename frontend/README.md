# CASCADE frontend

React + TypeScript + Vite + Tailwind v4 + `@xyflow/react`.

```bash
npm install
cp .env.example .env     # optional; defaults to http://localhost:8000
npm run dev              # http://localhost:5173 (already allowed by the backend's CORS list)
npm run build
```

Start the API first: `uvicorn app.main:app --port 8000` from `backend/`.
