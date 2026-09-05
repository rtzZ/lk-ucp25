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

export interface Grade {
  id: number;
  subject: string;
  semester: string;
  attestation: string;
  value: string;
  verbal: string;
  ects: string;
  score: number | null;
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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json() as Promise<T>;
}

export const api = {
  groups: () => get<string[]>("/schedule/groups"),
  students: (group: string) =>
    get<Student[]>(`/students?group=${encodeURIComponent(group)}`),
  login: async (last_name: string, first_name: string) => {
    const r = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ last_name, first_name }),
    });
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
  schedule: (group: string, kind = "") =>
    get<ScheduleItem[]>(
      `/schedule?group=${encodeURIComponent(group)}` +
        (kind ? `&kind=${kind}` : "")
    ),
  grades: (student_id: number) =>
    get<Grade[]>(`/grades?student_id=${student_id}`),
};
