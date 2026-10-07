/** HTTP-клиент backend API. */

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export interface Student {
  id: number;
  group: string;
  code: string;
  last_name: string;
  first_name: string;
  full_name: string;
}

export interface SubjectDescription {
  about: string;
  skills_title: string | null;
  skills: string[];
  content_title: string | null;
  content: string[];
}

export interface Subject {
  id: number;
  name: string;
  description: SubjectDescription;
}

export interface Grade {
  id: number;
  subject: string;
  semester: string;
  attestation: string;
  value: string;
  verbal: string;
  ects: string;
  score: number | null;
  description: SubjectDescription;
}

export interface ScheduleItem {
  id: number;
  group: string;
  date: string;
  time_start: string;
  time_end: string;
  subject_text: string;
  teacher: string;
  org: string;
  lesson_no: number | null;
  kind: string;
  status: string;
  note: string;
  link: string;
}

const TOKEN_KEY = "lk-token";

/** Токен сессии (Authorization: Bearer). localStorage недоступен — без сессии. */
export const session = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* приватный режим: сессия живёт до перезагрузки */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* нечего чистить */
    }
  },
};

/** Ответ 401: токен истёк/отозван — App переводит на экран входа. */
export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function req(path: string, init?: RequestInit, timeoutMs = 15000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const token = session.get();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  try {
    return await fetch(`${API}${path}`, { ...init, headers, signal: ctrl.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`timeout ${path}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function get<T>(path: string): Promise<T> {
  const r = await req(path);
  if (r.status === 401) {
    onUnauthorized();
    throw new UnauthorizedError();
  }
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json() as Promise<T>;
}

async function postJson(path: string, body: unknown): Promise<Response> {
  return req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Ошибка API с текстом для пользователя (detail backend'а). */
async function apiError(r: Response, fallback: string): Promise<Error> {
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") return new Error(body.detail);
  } catch {
    /* не JSON */
  }
  return new Error(fallback);
}

export interface AuthConfig {
  telegram: boolean;
  bot_username: string;
  dev_mode: boolean;
}

export interface RequestPasswordResult {
  sent: boolean;
  dev_password: string | null;
}

export const api = {
  authConfig: () => get<AuthConfig>("/auth/config"),
  requestPassword: async (
    last_name: string,
    first_name: string
  ): Promise<RequestPasswordResult> => {
    const r = await postJson("/auth/request_password", { last_name, first_name });
    if (!r.ok) throw await apiError(r, "Не удалось запросить пароль");
    return r.json();
  },
  login: async (last_name: string, first_name: string, password: string) => {
    const r = await postJson("/auth/login", { last_name, first_name, password });
    if (!r.ok) throw await apiError(r, "Не удалось войти");
    const body = (await r.json()) as { token: string; student: Student };
    session.set(body.token);
    return body.student;
  },
  logout: async () => {
    try {
      await postJson("/auth/logout", {});
    } finally {
      session.clear();
    }
  },
  me: () => get<Student>("/auth/me"),
  schedule: (kind = "") =>
    get<ScheduleItem[]>(
      "/schedule" + (kind ? `?kind=${encodeURIComponent(kind)}` : "")
    ),
  grades: () => get<Grade[]>("/grades"),
  subject: (name: string) =>
    get<Subject>(`/subjects?name=${encodeURIComponent(name)}`),
};
