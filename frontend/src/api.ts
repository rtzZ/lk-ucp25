/** HTTP-клиент backend API. */

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

async function req(path: string, init?: RequestInit, timeoutMs = 15000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(`${API}${path}`, { ...init, signal: ctrl.signal });
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

export const api = {
  groups: () => get<string[]>("/schedule/groups"),
  students: (group: string) =>
    get<Student[]>(`/students?group=${encodeURIComponent(group)}`),
  /** Студент по стабильному code; null — больше нет в ведомости (404). */
  studentByCode: async (code: string): Promise<Student | null> => {
    const r = await req(`/students/by_code?code=${encodeURIComponent(code)}`);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`${r.status} /students/by_code`);
    return r.json() as Promise<Student>;
  },
  login: async (last_name: string, first_name: string) => {
    const r = await postJson("/auth/login", { last_name, first_name });
    const body = await r.json();
    if (!r.ok) {
      const err = new Error("login failed") as Error & {
        suggestions?: Student[];
      };
      err.suggestions = body?.detail?.suggestions ?? [];
      throw err;
    }
    return body.student as Student;
  },
  telegramRequestCode: async (username: string) => {
    const r = await postJson("/auth/telegram_request_code", {
      telegram_username: username,
    });
    return r.json();
  },
  telegramLogin: async (username: string, code: string) => {
    const r = await postJson("/auth/telegram_login", {
      telegram_username: username,
      code,
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || "Telegram login failed");
    return body.student as Student;
  },
  schedule: (group: string, kind = "") =>
    get<ScheduleItem[]>(
      `/schedule?group=${encodeURIComponent(group)}` +
        (kind ? `&kind=${kind}` : "")
    ),
  grades: (student_id: number) =>
    get<Grade[]>(`/grades?student_id=${student_id}`),
  subject: (name: string) =>
    get<Subject>(`/subjects?name=${encodeURIComponent(name)}`),
};
