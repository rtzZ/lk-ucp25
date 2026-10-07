/** Оценки студента по официальной шкале (разбор — backend, app/grading.py).
 *  Десктоп — таблица Atlassian с фильтрами/сортировкой в шапке,
 *  телефон — карточки. */

import { useEffect, useMemo, useState } from "react";
import Button from "@atlaskit/button/new";
import { DynamicTableStateless } from "@atlaskit/dynamic-table";
import Heading from "@atlaskit/heading";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import SortAscendingIcon from "@atlaskit/icon/core/sort-ascending";
import SortDescendingIcon from "@atlaskit/icon/core/sort-descending";
import { CheckboxOption } from "@atlaskit/select/checkbox-option";
import { PopupSelect } from "@atlaskit/select/popup-select";
import { Inline, Stack } from "@atlaskit/primitives/compiled";
import { SimpleTag } from "@atlaskit/tag";
import Toggle from "@atlaskit/toggle";
import { api, type Grade, type Student } from "../api";
import { semesterNumber, semesterNumeral } from "../semesters";
import Sheet from "../components/Sheet";
import SubjectDescriptionView from "../components/SubjectDescription";
import {
  EctsValue,
  GradeValue,
  ScaleTable,
  ScoreBar,
  gradeKey,
  gradeMeta,
  gradeRank,
} from "../components/GradeParts";

type SortKey = "subject" | "semester" | "value" | "ects";
type SortOrder = "ASC" | "DESC";

const TITLES: Record<SortKey, string> = {
  subject: "Предмет",
  semester: "Семестр",
  value: "Оценка",
  ects: "ECTS",
};

const CLEAR_ALL = "__clear__";

/** 1 оценке, 2 оценкам, 5 оценкам (дательный падеж). */
function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

const NARROW_QUERY = "(max-width: 560px)";

/** Узкий экран (телефон): таблица не влезает — показываем карточки. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

export default function Grades({ student }: { student: Student }) {
  const [grades, setGrades] = useState<Grade[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("semester");
  const [sortOrder, setSortOrder] = useState<SortOrder>("ASC");
  const [filters, setFilters] = useState<Record<SortKey, string[]>>({
    subject: [],
    semester: [],
    value: [],
    ects: [],
  });
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);
  const [scaleOpen, setScaleOpen] = useState(false);
  // «Актуальное» — только текущий (последний в ведомости) семестр,
  // как тумблер «Актуальное / Всё расписание» на вкладке расписания.
  const [currentOnly, setCurrentOnly] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    api.grades()
      .then((g) => {
        setGrades(g);
        setLoadError("");
      })
      .catch(() => {
        setGrades([]);
        setLoadError("Не удалось загрузить оценки. Проверьте соединение.");
      })
      .finally(() => setLoading(false));
  }, [student.id]);

  // Сброс на первую страницу при смене фильтров/сортировки.
  useEffect(() => {
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, sortKey, sortOrder, currentOnly]);

  const currentSemester = useMemo(
    () => Math.max(0, ...grades.map((g) => semesterNumber(g.semester) ?? 0)),
    [grades]
  );

  const columns: SortKey[] = ["subject", "semester", "value", "ects"];

  // Значение колонки для фильтра — уже нормализованное по шкале:
  // «Отлично» и «5» из ведомости — одна опция «5».
  const cell = (g: Grade, k: SortKey): string =>
    k === "semester" ? semesterNumeral(g.semester)
      : k === "value" ? gradeKey(g)
        : k === "ects" ? g.ects_letter || "—"
          : g.subject;

  const uniq = (key: SortKey) => {
    const vals = [...new Set(grades.map((g) => cell(g, key)))];
    if (key === "value") {
      const rank = new Map(grades.map((g) => [gradeKey(g), gradeRank(g)]));
      return vals.sort((a, b) => (rank.get(b) ?? 0) - (rank.get(a) ?? 0));
    }
    return vals.sort((a, b) => a.localeCompare(b, "ru"));
  };

  const cycleSort = (key: SortKey) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortOrder("ASC");
    } else {
      setSortOrder((o) => (o === "ASC" ? "DESC" : "ASC"));
    }
  };

  const visible = useMemo(() => {
    const filtered = grades.filter((g) =>
      (!currentOnly || semesterNumber(g.semester) === currentSemester) &&
      columns.every((k) => filters[k].length === 0 || filters[k].includes(cell(g, k)))
    );
    const dir = sortOrder === "ASC" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === "semester") {
        return ((semesterNumber(a.semester) ?? 999) - (semesterNumber(b.semester) ?? 999)) * dir;
      }
      if (sortKey === "value") return (gradeRank(b) - gradeRank(a)) * dir;
      return cell(a, sortKey).localeCompare(cell(b, sortKey), "ru") * dir;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grades, filters, sortKey, sortOrder, currentOnly, currentSemester]);

  // Средний балл — по пятибалльным эквивалентам итоговых оценок
  // (в т.ч. записанных словом: «Отлично» = 5), без предварительных.
  const final = grades.filter((g) => g.status === "final");
  const fives = final.map((g) => g.five).filter((f): f is number => f !== null);
  const avg = fives.length > 0
    ? (fives.reduce((a, b) => a + b, 0) / fives.length).toFixed(2)
    : "—";
  const scores = final.map((g) => g.score).filter((s): s is number => s !== null);
  const avg100 = scores.length > 0
    ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1).replace(".", ",")
    : "";
  const inProgress = grades.filter((g) => g.status === "in_progress").length;
  const mismatches = grades.filter((g) => g.mismatch).length;
  const hasFilter = Object.values(filters).some((v) => v.length > 0);
  const narrow = useNarrow();
  const emptyText = hasFilter ? "Нет оценок по фильтру." : "Оценок пока нет.";

  const subjectLink = (g: Grade) => (
    <span
      role="button"
      tabIndex={0}
      className="subject-link"
      onClick={() => setSelectedSubject(g.subject)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setSelectedSubject(g.subject);
        }
      }}
    >
      {g.subject}
    </span>
  );


  const headCell = (key: SortKey) => (
    <span className="head-merged">
      <PopupSelect
        components={{ Option: CheckboxOption }}
        options={[
          { label: "Очистить всё", value: CLEAR_ALL },
          ...uniq(key).map((v) => ({ label: v, value: v })),
        ]}
        isMulti
        closeMenuOnSelect={false}
        hideSelectedOptions={false}
        label={`Фильтр: ${TITLES[key]}`}
        placeholder=""
        value={filters[key].map((v) => ({ label: v, value: v }))}
        onChange={(o) => {
          const picked = Array.isArray(o) ? o.map((x) => x.value) : [];
          setFilters((f) => ({
            ...f,
            [key]: picked.includes(CLEAR_ALL) ? [] : picked,
          }));
        }}
        target={({ isOpen, ...triggerProps }) => (
          <Button
            {...triggerProps}
            aria-label={`Фильтр: ${TITLES[key]}`}
            isSelected={isOpen}
            iconAfter={ChevronDownIcon}
          >
            {TITLES[key]}
            {filters[key].length > 0 ? ` · ${filters[key].length}` : ""}
          </Button>
        )}
      />
      <button
        type="button"
        className={sortKey === key ? "sort-btn active" : "sort-btn"}
        aria-label={`Сортировка: ${TITLES[key]}`}
        title={
          sortKey !== key
            ? "Сортировать"
            : sortOrder === "ASC" ? "По возрастанию" : "По убыванию"
        }
        onClick={() => cycleSort(key)}
      >
        {sortKey === key && sortOrder === "DESC" ? (
          <SortDescendingIcon label="" size="small" />
        ) : (
          <SortAscendingIcon label="" size="small" />
        )}
      </button>
    </span>
  );

  return (
    <div>
      {/* Тумблер — на том же месте, что и на вкладке «Расписание»:
          первой строкой под вкладками. */}
      <div className="schedule-top">
        <label className="toggle-row">
          <Toggle
            label="Актуальное"
            isChecked={currentOnly}
            onChange={(e) => setCurrentOnly((e.target as HTMLInputElement).checked)}
          />
          <span>{currentOnly ? "Актуальное" : "Все оценки"}</span>
        </label>
      </div>
      {/* Имя уже в шапке — здесь только итог. */}
      <div className="summary">
        <div>
          <div className="detail-label">Средний балл</div>
          <div className="summary-value">{avg}</div>
          <div className="meta">
            по {fives.length} {plural(fives.length, "оценке", "оценкам", "оценкам")}
            {avg100 && <> · по 100-балльной: {avg100}</>}
          </div>
        </div>
        <div className="summary-side">
          <Button appearance="subtle" onClick={() => setScaleOpen(true)}>
            Шкала оценивания
          </Button>
          <div className="meta summary-note">
            {inProgress > 0 && <>идёт: {inProgress}</>}
            {inProgress > 0 && mismatches > 0 && " · "}
            {mismatches > 0 && <>⚠ расходится со шкалой: {mismatches}</>}
          </div>
        </div>
      </div>
      {loadError && <p className="error">{loadError}</p>}
      {narrow ? (
        <>
          {/* Телефон: те же фильтры/сортировка строкой над карточками. */}
          <div className="grade-toolbar">
            {columns.map((key) => (
              <span key={key}>{headCell(key)}</span>
            ))}
          </div>
          {loading ? (
            <p className="meta">Загрузка…</p>
          ) : visible.length === 0 ? (
            <p>{emptyText}</p>
          ) : (
            <ul className="grade-cards" aria-label="Оценки">
              {visible.map((g) => (
                <li key={g.id} className="grade-card">
                  <div className="grade-card-main">
                    {subjectLink(g)}
                    <div className="meta">{gradeMeta(g, semesterNumeral(g.semester))}</div>
                    {g.status === "in_progress" && <ScoreBar score={g.score ?? 0} />}
                    {g.mismatch && <div className="grade-warning">⚠ {g.mismatch}</div>}
                  </div>
                  <GradeValue g={g} inCard />
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <DynamicTableStateless
          head={{ cells: columns.map((key) => ({ key, content: headCell(key) })) }}
          rows={visible.map((g) => ({
            key: `grade-${g.id}`,
            cells: [
              { key: g.subject, content: subjectLink(g) },
              { key: g.semester, content: semesterNumeral(g.semester) },
              { key: `${gradeKey(g)}|${g.id}`, content: <GradeValue g={g} withLabel /> },
              { key: `${g.ects_letter}|${g.id}`, content: <EctsValue g={g} /> },
            ],
          }))}
          rowsPerPage={50}
          page={page}
          onSetPage={setPage}
          isLoading={loading}
          emptyView={<p>{emptyText}</p>}
        />
      )}
      {selectedSubject && (
        <Sheet
          onClose={() => setSelectedSubject(null)}
          label={`Предмет: ${selectedSubject}`}
        >
            <Stack space="space.200">
              <Heading size="medium" as="h2">
                {selectedSubject}
              </Heading>
              <Stack space="space.100">
                {grades
                  .filter((g) => g.subject === selectedSubject)
                  .map((g) => (
                    <Stack key={g.id} space="space.050">
                      <Inline space="space.100" alignBlock="center">
                        <SimpleTag text={`${semesterNumeral(g.semester)} семестр`} />
                        <GradeValue g={g} withLabel />
                        <EctsValue g={g} />
                      </Inline>
                      {g.status === "provisional" && (
                        <div className="meta">
                          Предварительно: в ведомости оценки нет, посчитано по баллам.
                        </div>
                      )}
                      {g.mismatch && <div className="grade-warning">⚠ {g.mismatch}</div>}
                    </Stack>
                  ))}
              </Stack>
              <SubjectDescriptionView
                description={
                  grades.find((g) => g.subject === selectedSubject)?.description
                }
              />
            </Stack>
        </Sheet>
      )}
      {scaleOpen && (
        <Sheet onClose={() => setScaleOpen(false)} label="Шкала оценивания">
          <Stack space="space.200">
            <Heading size="medium" as="h2">
              Шкала оценивания
            </Heading>
            <ScaleTable grades={grades} />
          </Stack>
        </Sheet>
      )}
    </div>
  );
}
