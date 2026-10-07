/** Расписание группы, сгруппированное по датам. Клик по паре — drawer. */

import { useEffect, useState, type ReactNode } from "react";
import Avatar from "@atlaskit/avatar";
import Button, { LinkButton } from "@atlaskit/button/new";
import { DatePicker, TimePicker } from "@atlaskit/datetime-picker";
import { Drawer, DrawerCloseButton, DrawerContent } from "@atlaskit/drawer";
import { Label } from "@atlaskit/form";
import Heading from "@atlaskit/heading";
import CalendarIcon from "@atlaskit/icon/core/calendar";
import VideoIcon from "@atlaskit/icon/core/video";
import Lozenge from "@atlaskit/lozenge";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import Toggle from "@atlaskit/toggle";
import { api, type ScheduleItem, type SubjectDescription } from "../api";
import { downloadIcs } from "../ics";
import { semesterInfo } from "../semesters";
import DescriptionTextArea from "../components/SubjectDescription";

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

/** Строка деталей drawer: подпись (Label) + значение. */
function Detail({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <Stack space="space.050">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </Stack>
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

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
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
      </div>
      <div className="filters">
        {[
          { value: "", label: "Всё" },
          { value: "lesson", label: "Пара" },
          { value: "attestation", label: "Аттестация" },
          { value: "deadline", label: "Дедлайн" },
        ].map((f) => (
          <button
            key={f.value || "all"}
            className={kind === f.value ? "chip active" : "chip"}
            onClick={() => setKind(f.value)}
          >
            {f.label}
          </button>
        ))}
        <button
          className="chip add-calendar"
          onClick={() => downloadIcs([...byDate.values()].flat())}
        >
          Добавить в календарь
        </button>
      </div>
      {loading && <p>Загрузка…</p>}
      {!loading && loadError && <p className="error">{loadError}</p>}
      {!loading && !loadError && byDate.size === 0 && <p>Нет записей.</p>}
      {[...byDate.entries()].map(([date, list]) => {
        const sem = semesterInfo(date);
        return (
          <section key={date} className="day">
            <h3>{formatDate(date)}</h3>
            {sem && (
              <div className="meta">
                {sem.numeral} семестр · {sem.academicYear} уч. год
              </div>
            )}
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
                {it.time_start && (
                  <span className="time">{it.time_start}–{it.time_end}</span>
                )}
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
      {selected && (
        <Drawer
          isOpen
          onClose={() => setSelected(null)}
          label={`Занятие: ${selected.subject_text}`}
          width="narrow"
        >
          <DrawerCloseButton />
          <DrawerContent>
            <Box paddingInlineStart="space.0" paddingInlineEnd="space.400">
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
<Detail id="lesson-date" label="Дата">
                  <DatePicker
                    key={`date-${selected.id}`}
                    id="lesson-date"
                    defaultValue={selected.date}
                    dateFormat="DD.MM.YYYY"
                    isDisabled
                    appearance="subtle"
                  />
                </Detail>
                {selected.time_start && (
                  <Detail id="lesson-time" label="Время">
                    <Inline space="space.100" alignBlock="center">
                      <TimePicker
                        key={`time-${selected.id}`}
                        id="lesson-time"
                        defaultValue={selected.time_start}
                        timeFormat="HH:mm"
                        isDisabled
                        appearance="subtle"
                      />
                      {selected.time_end && (
                        <>
                          <Text as="p" color="color.text.subtle">
                            –
                          </Text>
                          <TimePicker
                            key={`time-end-${selected.id}`}
                            id="lesson-time-end"
                            defaultValue={selected.time_end}
                            timeFormat="HH:mm"
                            isDisabled
                            appearance="subtle"
                          />
                        </>
                      )}
                    </Inline>
                  </Detail>
                )}
                {selected.teacher && (
                  <Detail id="lesson-teacher" label="Преподаватель">
                    <Inline space="space.100" alignBlock="center">
                      <Avatar size="small" name={selected.teacher} />
                      <Text id="lesson-teacher">{selected.teacher}</Text>
                    </Inline>
                  </Detail>
                )}
                {selected.org && (
                  <Detail id="lesson-org" label="Организация">
                    <Text as="p">
                      {selected.org}
                    </Text>
                  </Detail>
                )}
                {selected.note && (
                  <Detail id="lesson-note" label="Заметка">
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
              <DescriptionTextArea description={subjectDesc} />
              </Stack>
            </Box>
          </DrawerContent>
        </Drawer>
      )}
    </div>
  );
}
