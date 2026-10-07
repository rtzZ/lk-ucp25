/** Расписание группы, сгруппированное по датам. Клик по паре — drawer. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import Avatar from "@atlaskit/avatar";
import Button, { LinkButton } from "@atlaskit/button/new";
import Heading from "@atlaskit/heading";
import CalendarIcon from "@atlaskit/icon/core/calendar";
import VideoIcon from "@atlaskit/icon/core/video";
import Lozenge from "@atlaskit/lozenge";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import Toggle from "@atlaskit/toggle";
import { api, type ScheduleItem, type SubjectDescription } from "../api";
import { downloadIcs } from "../ics";
import { semesterInfo } from "../semesters";
import Sheet from "../components/Sheet";
import SubjectDescriptionView from "../components/SubjectDescription";

const KIND_LABEL: Record<string, string> = {
  lesson: "Пара",
  attestation: "Аттестация",
  event: "Событие",
  deadline: "Дедлайн",
};

const KIND_APPEARANCE: Record<string, "default" | "inprogress" | "new" | "removed" | "moved" | "success"> = {
  lesson: "inprogress",
  attestation: "new",
  event: "default",
  deadline: "moved",
};

/** Строка деталей drawer: подпись + значение обычным текстом.
 *  Не disabled-поля формы: они серые и читаются как «недоступно». */
function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="detail">
      <div className="detail-label">{label}</div>
      <div className="detail-value">{children}</div>
    </div>
  );
}

/** Единый статус пары: один текст и вид в карточках расписания и в drawer. */
const STATUS_APPEARANCE = {
  live: "success",
  cancelled: "removed",
  moved: "moved",
  completed: "default",
  active: "inprogress",
} as const;

const STATUS_LABEL: Record<string, string> = {
  live: "Идёт сейчас",
  cancelled: "Отменено",
  moved: "Перенесено",
  completed: "Завершено",
  active: "Запланировано",
};

/** «Четверг, 8 октября» (+ год, если не текущий). Заглавная — только первая
 *  буква: CSS capitalize давал «8 Октября 2026 Г.». */
export function formatDate(iso: string, now = new Date()): string {
  const [y, m, d] = iso.split("-").map(Number);
  const text = new Date(y, m - 1, d).toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    ...(y !== now.getFullYear() ? { year: "numeric" } : {}),
  });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Время пары: «19:00–20:20», одно начало или пусто. */
function timeRange(it: ScheduleItem): string {
  if (!it.time_start) return "";
  return it.time_end ? `${it.time_start}–${it.time_end}` : it.time_start;
}

/** Предстоящее событие: дата позже сегодня либо сегодня, но конец ещё впереди.
 *  Время сравнивается строками — часы добиваются нулём ('9:00' -> '09:00'),
 *  иначе лексикографическое сравнение врёт. */
export function isUpcoming(it: { date: string; time_end: string }, now = new Date()): boolean {
  const pad = (n: number | string) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  if (it.date > today) return true;
  if (it.date < today) return false;
  if (!it.time_end) return true;
  const [h, m] = it.time_end.split(":");
  return `${pad(h)}:${pad(m ?? "0")}` >= `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** Сегодня в ISO (локальная дата). */
function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const KIND_FILTERS = [
  { value: "", label: "Все типы" },
  { value: "lesson", label: "Пары" },
  { value: "attestation", label: "Аттестации" },
  { value: "event", label: "События" },
  { value: "deadline", label: "Дедлайны" },
];

export default function Schedule({ group }: { group: string }) {
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [upcomingOnly, setUpcomingOnly] = useState(true);
  const [kind, setKind] = useState("");
  const [selected, setSelected] = useState<ScheduleItem | null>(null);
  const [subjectDesc, setSubjectDesc] = useState<SubjectDescription | null>(null);

  useEffect(() => {
    if (!selected?.subject_text) {
      setSubjectDesc(null);
      return;
    }
    let cancelled = false;
    setSubjectDesc(null);
    api
      .subject(selected.subject_text)
      .then((s) => {
        if (!cancelled) setSubjectDesc(s.description);
      })
      .catch(() => {
        if (!cancelled) setSubjectDesc(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    let cancelled = false;
    const load = (initial: boolean) => {
      if (initial) setLoading(true);
      api.schedule(kind)
        .then((d) => {
          if (!cancelled) {
            setItems(d);
            setLoadError("");
          }
        })
        .catch(() => {
          if (!cancelled) {
            setItems([]);
            setLoadError("Не удалось загрузить расписание. Проверьте соединение.");
          }
        })
        .finally(() => {
          if (!cancelled && initial) setLoading(false);
        });
    };
    load(true);
    const timer = window.setInterval(() => load(false), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [group, kind]);

  const byDate = new Map<string, ScheduleItem[]>();
  for (const it of items) {
    if (upcomingOnly && !isUpcoming(it)) continue;
    const list = byDate.get(it.date) ?? [];
    list.push(it);
    byDate.set(it.date, list);
  }

  const liveItems = items.filter((it) => it.status === "live");

  // «Всё расписание» начинается с сентября прошлого года — прокрутка к сегодня.
  const listRef = useRef<HTMLDivElement>(null);
  const scrollToToday = (smooth = true) => {
    const today = todayIso();
    const target = [...(listRef.current?.querySelectorAll<HTMLElement>("[data-date]") ?? [])]
      .find((el) => (el.dataset.date ?? "") >= today);
    target?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  };
  const jumpPending = useRef(false);
  useEffect(() => {
    if (!upcomingOnly) jumpPending.current = true;
  }, [upcomingOnly]);
  useEffect(() => {
    if (jumpPending.current && !loading && items.length > 0) {
      jumpPending.current = false;
      scrollToToday(false);
    }
  });

  // Ссылка из таблицы — внешний источник: только http(s), иначе кнопка disabled.
  const lessonLink =
    selected?.link && /^https?:\/\//i.test(selected.link) ? selected.link : "";

  return (
    <div>
      {liveItems.length > 0 && (
        <div className="live-banner" role="status">
          <span className="live-dot" />
          <div>
            <div className="live-title">Идёт сейчас</div>
            <div className="live-subject">
              {liveItems
                .map((it) => `${it.subject_text} (${it.time_start}–${it.time_end})`)
                .join(", ")}
            </div>
          </div>
        </div>
      )}
      <div className="schedule-top">
        <label className="toggle-row">
          <Toggle
            label="Актуальное расписание"
            isChecked={upcomingOnly}
            onChange={(e) =>
              setUpcomingOnly((e.target as HTMLInputElement).checked)
            }
          />
          <span>{upcomingOnly ? "Актуальное" : "Всё расписание"}</span>
        </label>
        {!upcomingOnly && (
          <Button appearance="subtle" onClick={() => scrollToToday()}>
            Сегодня
          </Button>
        )}
      </div>
      <div className="filters" role="group" aria-label="Тип записи">
        {KIND_FILTERS.map((f) => (
          <button
            key={f.value || "all"}
            type="button"
            aria-pressed={kind === f.value}
            className={kind === f.value ? "chip active" : "chip"}
            onClick={() => setKind(f.value)}
          >
            {f.label}
          </button>
        ))}
        <span className="filters-end">
          <Button
            appearance="subtle"
            iconBefore={CalendarIcon}
            onClick={() => downloadIcs([...byDate.values()].flat())}
          >
            Добавить в календарь
          </Button>
        </span>
      </div>
      {loading && <p>Загрузка…</p>}
      {!loading && loadError && <p className="error">{loadError}</p>}
      {!loading && !loadError && byDate.size === 0 && <p>Нет записей.</p>}
      <div ref={listRef}>
      {[...byDate.entries()].map(([date, list], i, days) => {
        // Полоса семестра — только когда он сменился, а не под каждым днём.
        const sem = semesterInfo(date);
        const prev = i > 0 ? semesterInfo(days[i - 1][0]) : null;
        const semChanged =
          sem && (!prev || prev.numeral !== sem.numeral || prev.academicYear !== sem.academicYear);
        return (
          <section key={date} className="day" data-date={date}>
            {semChanged && (
              <div className="semester-divider">
                {sem.numeral} семестр · {sem.academicYear} уч. год
              </div>
            )}
            <h3>{formatDate(date)}</h3>
          {list.map((it) => (
            <article
              key={it.id}
              className={
                it.status === "cancelled"
                  ? "lesson cancelled"
                  : it.status === "completed"
                    ? "lesson completed"
                    : it.status === "live"
                      ? "lesson live"
                      : "lesson"
              }
              role="button"
              tabIndex={0}
              aria-label={`${it.subject_text}, ${formatDate(date)}`}
              onClick={() => setSelected(it)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setSelected(it);
              }}
            >
              <div className="lesson-head">
                <Lozenge appearance={KIND_APPEARANCE[it.kind] ?? "default"}>
                  {KIND_LABEL[it.kind] ?? it.kind}
                </Lozenge>
                {it.time_start && <span className="time">{timeRange(it)}</span>}
                {it.status !== "active" && (
                  <Lozenge
                    appearance={
                      STATUS_APPEARANCE[
                        it.status as keyof typeof STATUS_APPEARANCE
                      ]
                    }
                    isBold={it.status === "live"}
                  >
                    {STATUS_LABEL[it.status] ?? it.status}
                  </Lozenge>
                )}
              </div>
              <div className="subject">{it.subject_text}</div>
              {(it.teacher || it.org) && (
                <div className="meta">
                  {[it.teacher, it.org].filter(Boolean).join(" · ")}
                </div>
              )}
            </article>
          ))}
          </section>
        );
      })}
      </div>
      {selected && (
        <Sheet
          onClose={() => setSelected(null)}
          label={`Занятие: ${selected.subject_text}`}
        >
            <Box>
              <Stack space="space.200">
              <Heading size="medium" as="h2">
                {selected.subject_text || KIND_LABEL[selected.kind]}
              </Heading>
              <Inline space="space.100" alignBlock="center">
                <Lozenge appearance={KIND_APPEARANCE[selected.kind] ?? "default"}>
                  {KIND_LABEL[selected.kind] ?? selected.kind}
                </Lozenge>
                <Lozenge
                  appearance={
                    STATUS_APPEARANCE[
                      selected.status as keyof typeof STATUS_APPEARANCE
                    ] ?? "default"
                  }
                  isBold={selected.status === "live"}
                >
                  {STATUS_LABEL[selected.status] ?? selected.status}
                </Lozenge>
              </Inline>
              <Stack space="space.150">
<Detail label="Когда">
                  {formatDate(selected.date)}
                  {selected.time_start && (
                    <>
                      {" · "}
                      <span className="nowrap">{timeRange(selected)}</span>
                    </>
                  )}
                </Detail>
                {selected.teacher && (
                  <Detail label="Преподаватель">
                    <Inline space="space.100" alignBlock="center">
                      <Avatar size="small" name={selected.teacher} />
                      <Text>{selected.teacher}</Text>
                    </Inline>
                  </Detail>
                )}
                {selected.org && (
                  <Detail label="Организация">
                    <Text as="p">
                      {selected.org}
                    </Text>
                  </Detail>
                )}
                {selected.note && (
                  <Detail label="Заметка">
                    <Text as="p">
                      {selected.note}
                    </Text>
                  </Detail>
                )}
              </Stack>
              <Stack space="space.100">
                <Heading size="small" as="h3">
                  Действия
                </Heading>
                {lessonLink ? (
                  <LinkButton
                    appearance="primary"
                    href={lessonLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    iconBefore={VideoIcon}
                    shouldFitContainer
                  >
                    Подключиться к паре
                  </LinkButton>
                ) : (
                  <Button
                    appearance="primary"
                    isDisabled
                    iconBefore={VideoIcon}
                    shouldFitContainer
                  >
                    Подключиться к паре
                  </Button>
                )}
                <Button
                  appearance="default"
                  iconBefore={CalendarIcon}
                  shouldFitContainer
                  onClick={() => downloadIcs([selected])}
                >
                  Добавить в календарь
                </Button>
              </Stack>
              <SubjectDescriptionView description={subjectDesc} />
              </Stack>
            </Box>
        </Sheet>
      )}
    </div>
  );
}
