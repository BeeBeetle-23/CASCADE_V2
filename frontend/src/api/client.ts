import type {
  ApiErrorBody,
  ApplicationSummary,
  DashboardSummary,
  GraphPayload,
  ScenarioKey,
  SimulationResult,
} from "../types";

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(`Can't reach the CASCADE API at ${API_BASE}. Check that the backend is running.`, 0);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as ApiErrorBody;
      if (body.error) message = body.error;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  listApplications: () => request<ApplicationSummary[]>("/applications"),
  getGraph: (appId: string) => request<GraphPayload>(`/applications/${appId}/graph`),
  getSummary: (appId: string) => request<DashboardSummary>(`/applications/${appId}/summary`),
  loadScenario: (scenario: ScenarioKey) => post<GraphPayload>("/demo/load", { scenario }),
  reset: (scenario: ScenarioKey) => post<GraphPayload>("/demo/reset", { scenario }),
  simulate: (appId: string, excludedNodeId: string, actor = "analyst") =>
    post<SimulationResult>(`/applications/${appId}/simulate`, {
      excluded_node_id: excludedNodeId,
      actor,
    }),
};
