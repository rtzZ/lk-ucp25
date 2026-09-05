/** Расписание группы, сгруппированное по датам. Клик по паре — drawer. */

import { useEffect, useState } from "react";
import { Drawer, DrawerCloseButton, DrawerContent } from "@atlaskit/drawer";
import Lozenge from "@atlaskit/lozenge";
import Toggle from "@atlaskit/toggle";
import { api, type ScheduleItem } from "../api";
import { semesterInfo } from "../semesters";

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

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Предстоящее событие: дата позже сегодня либо сегодня, но конец ещё впереди. */
export function isUpcoming(it: { date: string; time_end: string }, now = new Date()): boolean {
  const pad = (n: number) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  if (it.date > today) return true;
  if (it.date < today) return false;
  if (!it.time_end) return true;
  return it.time_end >= `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export default function Schedule({ group }: { group: string }) {
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [kind, setKind] = useState("");
  const [loading, setLoading] = useState(true);
  const [upcomingOnly, setUpcomingOnly] = useState(true);
  const [selected, setSelected] = useState<ScheduleItem | null>(null);

  useEffect(() => {
    setLoading(true);
    api.schedule(group, kind).then(setItems).catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [group, kind]);

  const byDate = new Map<string, ScheduleItem[]>();
  for (const it of items) {
    if (upcomingOnly && !isUpcoming(it)) continue;
    const list = byDate.get(it.date) ?? [];
    list.push(it);
    byDate.set(it.date, list);
  }

  return (
    <div>
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
        {["", "lesson", "attestation", "deadline"].map((k) => (
          <button
            key={k}
            className={kind === k ? "chip active" : "chip"}
            onClick={() => setKind(k)}
          >
            {k === "" ? "Всё" : KIND_LABEL[k]}
          </button>
        ))}
      </div>
      {loading && <p>Загрузка…</p>}
      {!loading && byDate.size === 0 && <p>Нет записей.</p>}
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
              className={it.status !== "active" ? "lesson cancelled" : "lesson"}
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
                {it.status === "cancelled" && (
                  <Lozenge appearance="removed">Отмена</Lozenge>
                )}
                {it.status === "moved" && (
                  <Lozenge appearance="moved">Перенос</Lozenge>
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
            <h2>{selected.subject_text || KIND_LABEL[selected.kind]}</h2>
            <dl className="details">
              <div>
                <dt>Дата</dt>
                <dd>{formatDate(selected.date)}</dd>
              </div>
              {selected.time_start && (
                <div>
                  <dt>Время</dt>
                  <dd>{selected.time_start}–{selected.time_end}</dd>
                </div>
              )}
              {selected.teacher && (
                <div>
                  <dt>Преподаватель</dt>
                  <dd>{selected.teacher}</dd>
                </div>
              )}
              {selected.org && (
                <div>
                  <dt>Организация</dt>
                  <dd>{selected.org}</dd>
                </div>
              )}
              <div>
                <dt>Статус</dt>
                <dd>
                  {selected.status === "cancelled"
                    ? "Отменено"
                    : selected.status === "moved"
                      ? "Перенесено"
                      : "Запланировано"}
                </dd>
              </div>
              {selected.note && (
                <div>
                  <dt>Заметка</dt>
                  <dd>{selected.note}</dd>
                </div>
              )}
            </dl>
            <div className="link-row">
              <span className="link-label">Ссылка на подключение</span>
              {selected.link ? (
                <a href={selected.link} target="_blank" rel="noreferrer">
                  <Lozenge appearance="success" isBold>
                    Подключиться к паре
                  </Lozenge>
                </a>
              ) : (
                <Lozenge appearance="removed" isBold>
                  Ссылка не указана
                </Lozenge>
              )}
            </div>
          </DrawerContent>
        </Drawer>
      )}
    </div>
  );
}
