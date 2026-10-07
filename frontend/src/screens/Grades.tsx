/** Оценки студента: таблица Atlassian, шапка — единый popup-контрол:
 *  триггер с названием + popup с чекбоксами фильтра и стрелка сортировки. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Button from "@atlaskit/button/new";
import { Drawer, DrawerCloseButton, DrawerContent } from "@atlaskit/drawer";
import { DynamicTableStateless } from "@atlaskit/dynamic-table";
import Heading from "@atlaskit/heading";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import Lozenge from "@atlaskit/lozenge";
import { CheckboxOption } from "@atlaskit/select/checkbox-option";
import { PopupSelect } from "@atlaskit/select/popup-select";
import { Inline, Stack } from "@atlaskit/primitives/compiled";
import { SimpleTag } from "@atlaskit/tag";
import { api, type Grade, type Student } from "../api";
import { semesterNumber, semesterNumeral } from "../semesters";
import DescriptionTextArea from "../components/SubjectDescription";

type SortKey = "subject" | "semester" | "value" | "ects";
type SortOrder = "ASC" | "DESC";

function gradeAppearance(value: string): "success" | "inprogress" | "removed" | "default" {
  const v = value.trim().toLowerCase();
  if (["5", "отлично", "зачтено", "a", "b"].includes(v)) return "success";
  if (["4", "хорошо", "c"].includes(v)) return "inprogress";
  if (["2", "не зачтено", "незачтено"].includes(v)) return "removed";
  return "default";
}

/** Подпись оценки: «5 · Отлично»; пустая — оценки ещё нет (не «2»). */
function gradeLabel(g: Grade): string {
  if (!g.value.trim()) return "Нет оценки";
  return g.verbal && g.verbal.toLowerCase() !== g.value.toLowerCase()
    ? `${g.value} · ${g.verbal}`
    : g.value;
}

const TITLES: Record<SortKey, string> = {
  subject: "Предмет",
  semester: "Семестр",
  value: "Оценка",
  ects: "ECTS",
};

const PASS_VALUES = new Set(
  ["зачет", "зачёт", "зачтено", "не зачтено", "незачтено"].map((s) =>
    s.toLowerCase()
  )
);

/** Зачётный предмет: только шкала баллов, без букв и словесных. */
function isPassFail(g: Grade): boolean {
  return (
    PASS_VALUES.has(g.attestation.trim().toLowerCase()) ||
    PASS_VALUES.has(g.value.trim().toLowerCase())
  );
}

function ectsAppearance(letter: string): "success" | "inprogress" | "removed" | "moved" | "default" {
  const v = letter.trim().toLowerCase();
  if (["a", "b", "passed"].includes(v)) return "success";
  if (["c", "d"].includes(v)) return "inprogress";
  if (v === "e") return "moved";
  if (v === "f") return "removed";
  return "default";
}

function ectsCell(g: Grade): ReactNode {
  const score = g.score ?? null;
  if (isPassFail(g)) {
    const text = score !== null ? String(score) : "—";
    return <Lozenge appearance={score !== null ? "success" : "default"}>{text}</Lozenge>;
  }
  const letter = g.ects.trim() || "—";
  const text = score !== null && letter !== "—" ? `${letter} · ${score}` : letter;
  return <Lozenge appearance={ectsAppearance(letter)}>{text}</Lozenge>;
}

const CLEAR_ALL = "__clear__";

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
  }, [filters, sortKey, sortOrder]);

  const columns: SortKey[] = ["subject", "semester", "value", "ects"];

  const uniq = (key: SortKey) =>
    key === "semester"
      ? [...new Set(grades.map((g) => semesterNumeral(g.semester)))].sort()
      : [...new Set(grades.map((g) => g[key]).filter(Boolean))].sort((a, b) =>
          a.localeCompare(b, "ru")
        );

  const cycleSort = (key: SortKey) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortOrder("ASC");
    } else {
      setSortOrder((o) => (o === "ASC" ? "DESC" : "ASC"));
    }
  };

  const visible = useMemo(() => {
    const match = (g: Grade, k: SortKey) =>
      k === "semester" ? semesterNumeral(g.semester) : g[k];
    const filtered = grades.filter((g) =>
      columns.every((k) => filters[k].length === 0 || filters[k].includes(match(g, k)))
    );
    const dir = sortOrder === "ASC" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === "semester") {
        return ((semesterNumber(a.semester) ?? 999) - (semesterNumber(b.semester) ?? 999)) * dir;
      }
      return a[sortKey].localeCompare(b[sortKey], "ru") * dir;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grades, filters, sortKey, sortOrder]);

  const numeric = grades
    .map((g) => parseFloat(g.value))
    .filter((n) => !Number.isNaN(n) && n >= 2 && n <= 5);
  const avg = numeric.length > 0
    ? (numeric.reduce((a, b) => a + b, 0) / numeric.length).toFixed(2)
    : "—";

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

  const gradeLozenge = (g: Grade) => (
    <Lozenge appearance={gradeAppearance(g.value)}>{gradeLabel(g)}</Lozenge>
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
        onClick={() => cycleSort(key)}
      >
        {sortKey === key ? (sortOrder === "ASC" ? "▲" : "▼") : "△"}
      </button>
    </span>
  );

  return (
    <div>
      <div className="summary">
        <span>{student.full_name || `${student.last_name} ${student.first_name}`}</span>
        <Lozenge appearance="success" isBold>Средний балл: {avg}</Lozenge>
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
                  {subjectLink(g)}
                  <div className="grade-card-meta">
                    <SimpleTag text={`${semesterNumeral(g.semester)} семестр`} />
                    {gradeLozenge(g)}
                    {ectsCell(g)}
                  </div>
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
              { key: `${g.value}|${g.id}`, content: gradeLozenge(g) },
              { key: g.ects, content: ectsCell(g) },
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
        <Drawer
          isOpen
          onClose={() => setSelectedSubject(null)}
          label={`Предмет: ${selectedSubject}`}
          width="narrow"
        >
          <DrawerCloseButton />
          <DrawerContent>
            <Stack space="space.200">
              <Heading size="medium" as="h2">
                {selectedSubject}
              </Heading>
              <Stack space="space.100">
                {grades
                  .filter((g) => g.subject === selectedSubject)
                  .map((g) => (
                    <Inline key={g.id} space="space.100" alignBlock="center">
                      <SimpleTag text={semesterNumeral(g.semester)} />
                      {gradeLozenge(g)}
                    </Inline>
                  ))}
              </Stack>
              <DescriptionTextArea
                description={
                  grades.find((g) => g.subject === selectedSubject)?.description
                }
              />
            </Stack>
          </DrawerContent>
        </Drawer>
      )}
    </div>
  );
}
