/** Оценки студента: таблица Atlassian, шапка — единый popup-контрол:
 *  триггер с названием + popup с чекбоксами фильтра и стрелка сортировки. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Button from "@atlaskit/button/new";
import { Drawer, DrawerCloseButton, DrawerContent } from "@atlaskit/drawer";
import { DynamicTableStateless } from "@atlaskit/dynamic-table";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import Lozenge from "@atlaskit/lozenge";
import { CheckboxOption } from "@atlaskit/select/checkbox-option";
import { PopupSelect } from "@atlaskit/select/popup-select";
import { api, type Grade, type Student } from "../api";
import { semesterNumber, semesterNumeral } from "../semesters";

type SortKey = "subject" | "semester" | "value" | "ects";
type SortOrder = "ASC" | "DESC";

function gradeAppearance(value: string): "success" | "inprogress" | "removed" | "default" {
  const v = value.trim().toLowerCase();
  if (["5", "отлично", "зачтено", "a", "b"].includes(v)) return "success";
  if (["4", "хорошо", "c"].includes(v)) return "inprogress";
  if (["2", "не зачтено", "незачтено"].includes(v)) return "removed";
  return "default";
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

export default function Grades({ student }: { student: Student }) {
  const [grades, setGrades] = useState<Grade[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("semester");
  const [sortOrder, setSortOrder] = useState<SortOrder>("ASC");
  const [filters, setFilters] = useState<Record<SortKey, string[]>>({
    subject: [],
    semester: [],
    value: [],
    ects: [],
  });
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.grades(student.id).then(setGrades).catch(() => setGrades([]))
      .finally(() => setLoading(false));
  }, [student.id]);

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
      <DynamicTableStateless
        head={{ cells: columns.map((key) => ({ key, content: headCell(key) })) }}
        rows={visible.map((g) => ({
          key: `grade-${g.id}`,
          cells: [
            { key: g.subject, content: (
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
            )},
            { key: g.semester, content: semesterNumeral(g.semester) },
            { key: `${g.value}|${g.id}`, content: (
              <Lozenge appearance={gradeAppearance(g.value)}>
                {g.verbal && g.verbal.toLowerCase() !== g.value.toLowerCase()
                  ? `${g.value} · ${g.verbal}`
                  : g.value}
              </Lozenge>
            )},
            { key: g.ects, content: ectsCell(g) },
          ],
        }))}
        rowsPerPage={50}
        page={1}
        isLoading={loading}
        emptyView={<p>{hasFilter ? "Нет оценок по фильтру." : "Оценок пока нет."}</p>}
      />
      {selectedSubject && (
        <Drawer
          isOpen
          onClose={() => setSelectedSubject(null)}
          label={`Предмет: ${selectedSubject}`}
          width="narrow"
        >
          <DrawerCloseButton />
          <DrawerContent>
            <h2>{selectedSubject}</h2>
            <p>Информация о предмете недоступна.</p>
            <p>Для просмотра подробной информации обратитесь к преподавателю или в учебный отдел.</p>
          </DrawerContent>
        </Drawer>
      )}
    </div>
  );
}
