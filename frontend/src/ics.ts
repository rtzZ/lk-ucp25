/** Генерация *.ics (iCalendar) — порт алгоритма с www.pomidoruspekha.ru.
 *
 * События формируются из переданного набора занятий (того, что показано на
 * экране). Даты/время — локальные (floating), как на проде.
 */

import type { ScheduleItem } from "./api";

const DOMAIN = "lk.local";
const KIND_LABEL: Record<string, string> = {
  lesson: "Пара",
  attestation: "Аттестация",
  event: "Событие",
  deadline: "Дедлайн",
};

const STATUS_LABEL: Record<string, string> = {
  live: "Идёт сейчас",
  completed: "Прошло",
  cancelled: "Отменено",
  moved: "Перенесено",
};

/** Стабильный UID события: хэш смысловых полей.
 *
 * Старый вариант `lk-{id}` ломался при каждой синхронизации (wipe+insert
 * перегенерирует id) — повторный импорт плодил дубли в календарях.
 */
function stableUid(it: ScheduleItem): string {
  const s = [it.group, it.date, it.time_start, it.time_end,
    it.subject_text, it.kind].join("|");
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `lk-${h.toString(16).padStart(8, "0")}@${DOMAIN}`;
}

/** Длина строки в байтах (UTF-8) — для переноса строк iCalendar (<=75 октетов). */
function byteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

/** Экранирование текста iCalendar: \ ; , и переводы строк. */
function escapeText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r\n|\r|\n/g, "\\n");
}

/** «YYYYMMDDTHHMMSS» из даты и времени (локальное время, без таймзоны). */
function toDateTime(date: string, time: string): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = (time || "00:00").split(":").map(Number);
  return `${y}${pad(m || 1)}${pad(d || 1)}T${pad(hh || 0)}${pad(mm || 0)}00`;
}

/** Перенос строки длиннее 75 октетов: продолжение — CRLF + пробел. */
function fold(line: string): string {
  let out = "";
  let rest = line;
  const prefix = (continuation: boolean) => (continuation ? "" : " ");
  let first = true;
  while (byteLength(rest) > 75) {
    const budget = 75 - byteLength(prefix(first));
    let chars = 0;
    let octets = 0;
    for (const ch of rest) {
      const len = byteLength(ch);
      if (octets + len > budget) break;
      octets += len;
      chars += ch.length;
    }
    if (chars === 0) chars = budget - (budget % 2) || 1;
    out += prefix(first) + rest.slice(0, chars) + "\r\n";
    rest = rest.slice(chars);
    first = false;
  }
  return out + prefix(first) + rest;
}

/** Содержимое .ics для набора занятий. */
export function buildIcs(items: ScheduleItem[]): string {
  const dtstamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
  const lines: string[] = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    `PRODID:-//lk-app//RU`,
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
  ];
  for (const it of items) {
    const summary = it.subject_text || "Занятие";
    lines.push(
      "BEGIN:VEVENT",
      `UID:${stableUid(it)}`,
      `DTSTAMP:${dtstamp}`,
      `DTSTART:${toDateTime(it.date, it.time_start)}`,
      `DTEND:${toDateTime(it.date, it.time_end || "23:59")}`,
      `SUMMARY:${escapeText(summary)}`
    );
    const desc: string[] = [];
    if (it.teacher) desc.push(`Преподаватель: ${it.teacher}`);
    if (it.org) desc.push(`Организация: ${it.org}`);
    if (it.kind) desc.push(`Тип: ${KIND_LABEL[it.kind] ?? it.kind}`);
    if (it.status && it.status !== "active")
      desc.push(`Статус: ${STATUS_LABEL[it.status] ?? it.status}`);
    if (it.note) desc.push(it.note);
    if (desc.length) lines.push(`DESCRIPTION:${escapeText(desc.join("\n"))}`);
    // URL — это URI (RFC 5545): экранировать ; , нельзя, только переносить.
    if (it.link) lines.push(`URL:${it.link.replace(/\s+/g, "")}`);
    lines.push(`LOCATION:${escapeText(it.org || "")}`, "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return (
    lines.flatMap((line) => line.split("\n").map(fold)).join("\r\n") + "\r\n"
  );
}

/** Скачивание .ics-файла через Blob. */
export function downloadIcs(
  items: ScheduleItem[],
  filename = "raspisanie.ics"
): void {
  const blob = new Blob([buildIcs(items)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}