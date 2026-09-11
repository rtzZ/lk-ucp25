/** Семестры: канонические границы и римские номера для UI. */

export interface SemesterRange {
  n: number;
  numeral: string;
  from: string; // ISO
  to: string; // ISO
}

export const SEMESTERS: SemesterRange[] = [
  { n: 1, numeral: "I", from: "2025-09-01", to: "2026-02-08" },
  { n: 2, numeral: "II", from: "2026-02-09", to: "2026-07-04" },
  { n: 3, numeral: "III", from: "2026-09-01", to: "2027-01-30" },
  { n: 4, numeral: "IV", from: "2027-02-01", to: "2027-06-30" },
];

const ROMAN = ["I", "II", "III", "IV", "V", "VI"];

/** «1 семестр 25-26» -> 1. */
export function semesterNumber(name: string): number | null {
  const m = /(\d+)/.exec(name);
  return m ? parseInt(m[1], 10) : null;
}

/** «1 семестр 25-26» -> «I». Не распознано — как есть. */
export function semesterNumeral(name: string): string {
  const n = semesterNumber(name);
  return n !== null && n >= 1 && n <= ROMAN.length ? ROMAN[n - 1] : name;
}

/** Номер семестра по дате (для расписания). Вне диапазонов — null. */
export function semesterByDate(iso: string): number | null {
  const hit = SEMESTERS.find((s) => s.from <= iso && iso <= s.to);
  return hit ? hit.n : null;
}

export interface SemesterInfo {
  numeral: string;
  academicYear: string; // «2025/26»
}

/** Семестр и учебный год даты: «II семестр · 2025/26». Вне диапазонов — null. */
export function semesterInfo(iso: string): SemesterInfo | null {
  const hit = SEMESTERS.find((s) => s.from <= iso && iso <= s.to);
  if (!hit) return null;
  // Учебный год начинается в сентябре.
  const startYear = parseInt(hit.from.slice(0, 4), 10);
  const startMonth = parseInt(hit.from.slice(5, 7), 10);
  const y1 = startMonth >= 9 ? startYear : startYear - 1;
  return {
    numeral: hit.numeral,
    academicYear: `${y1}/${String(y1 + 1).slice(2)}`,
  };
}
