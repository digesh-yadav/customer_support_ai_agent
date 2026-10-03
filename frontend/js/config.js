// Where the backend runs. Local dev -> localhost:8000, deployed -> same origin.
const API_BASE = (location.protocol === "file:" || ["localhost", "127.0.0.1"].includes(location.hostname))
  ? "http://localhost:8000"   // local development
  : "";                        // deployed (Vercel): same origin, /api/* is rewritten to the backend
