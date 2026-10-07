/** Отображение оценки по официальной шкале (разбор делает backend,
 *  app/grading.py): значение, прогресс баллов, расхождение с ведомостью,
 *  легенда шкалы. Здесь нет своих списков «что считать пятёркой». */

import { useEffect, useState } from "react";
import WarningIcon from "@atlaskit/icon/core/warning";
import { api, type Grade, type ScaleBand } from "../api";

/** Порог зачёта и границы букв шкалы — отметки на полоске прогресса. */
export const PASS_SCORE = 55;
const TICKS = [55, 65, 75, 85, 95];

type Tone = "success" | "information" | "warning" | "danger" | "default";

/** Цвет оценки: 5 — зелёный, 4 — синий, 3 — жёлтый, 2/не зачтено — красный. */
export function gradeTone(g: Pick<Grade, "five" | "passed">): Tone {
  if (g.five !== null) {
    return g.five === 5 ? "success" : g.five === 4 ? "information"
      : g.five === 3 ? "warning" : "danger";
  }
  if (g.passed !== null) return g.passed ? "success" : "danger";
  return "default";
}

const ECTS_TONE: Record<string, Tone> = {
  A: "success", B: "success", C: "information", D: "information", E: "warning", F: "danger",
};

/** Подпись оценки для фильтра/сортировки: «5», «Зачтено», «Идёт», «Нет оценки». */
export function gradeKey(g: Grade): string {
  if (g.status === "in_progress") return "Идёт";
  if (g.status === "none") return "Нет оценки";
  if (g.five !== null) return String(g.five);
  if (g.passed !== null) return g.passed ? "Зачтено" : "Не зачтено";
  const v = g.value.trim();
  return v.charAt(0).toUpperCase() + v.slice(1);
}

/** Порядок сортировки по оценке: 5, 4, 3, 2, зачтено, не зачтено, идёт, нет. */
export function gradeRank(g: Grade): number {
  if (g.status === "in_progress") return 1;
  if (g.status === "none") return 0;
  if (g.five !== null) return 10 + g.five;
  if (g.passed !== null) return g.passed ? 5 : 4;
  return 3;
}

function fmt(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1).replace(".", ",");
}

/** Оценка крупно и цветом. Предварительная — приглушена и подписана.
 *  inCard: в карточке баллы текущего семестра уже на полоске — справа «Идёт». */
export function GradeValue({
  g,
  withLabel = false,
  inCard = false,
}: {
  g: Grade;
  withLabel?: boolean;
  inCard?: boolean;
}) {
  if (g.status === "none") {
    return <span className="grade-value grade-none">Нет оценки</span>;
  }
  if (g.status === "in_progress" && inCard) {
    return <span className="grade-value grade-none">Идёт</span>;
  }
  if (g.status === "in_progress") {
    return (
      <span className="grade-value grade-none">
        {fmt(g.score ?? 0)} <span className="grade-verbal">из 100</span>
      </span>
    );
  }
  const provisional = g.status === "provisional";
  const main = g.five !== null ? String(g.five) : gradeKey(g);
  const label = withLabel && g.five !== null ? g.label : "";
  return (
    <span
      className={`grade-value grade-${gradeTone(g)}${provisional ? " grade-provisional" : ""}`}
      title={provisional ? "Предварительно: в ведомости оценки нет, посчитано по баллам" : undefined}
    >
      <span className={g.five !== null ? "grade-number" : "grade-word"}>
        {provisional ? `≈${main}` : main}
      </span>
      {label && <span className="grade-verbal">{label}</span>}
      {g.mismatch && <MismatchIcon text={g.mismatch} />}
    </span>
  );
}

/** Значок расхождения ведомости со шкалой (текст — в title и для скринридера). */
export function MismatchIcon({ text }: { text: string }) {
  return (
    <span className="grade-mismatch" title={text}>
      <WarningIcon label={`Расходится со шкалой: ${text}`} size="small" />
    </span>
  );
}

/** Буква ECTS (+ баллы); «по баллам» — если в ведомости буквы нет. */
export function EctsValue({ g }: { g: Grade }) {
  if (g.status === "in_progress") return <ScoreBar score={g.score ?? 0} compact />;
  const letter = g.ects_letter;
  if (!letter) {
    return <span className="ects ects-default">{g.score !== null ? fmt(g.score) : "—"}</span>;
  }
  return (
    <span
      className={`ects ects-${ECTS_TONE[letter] ?? "default"}`}
      title={g.ects_source === "score" ? "В ведомости буквы нет — по баллам и шкале" : undefined}
    >
      {letter}
      {g.score !== null && ` · ${fmt(g.score)}`}
      {g.ects_source === "score" && <span className="ects-src">по баллам</span>}
    </span>
  );
}

/** Полоска набранных баллов с отметками шкалы (55 — порог зачёта). */
export function ScoreBar({ score, compact = false }: { score: number; compact?: boolean }) {
  const pct = Math.max(0, Math.min(100, score));
  const left = Math.max(0, PASS_SCORE - score);
  return (
    <div className={compact ? "score-bar compact" : "score-bar"}>
      <div
        className="score-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-label={`Набрано ${fmt(score)} из 100`}
      >
        <div className="score-fill" style={{ width: `${pct}%` }} />
        {TICKS.map((t) => (
          <span key={t} className={t === PASS_SCORE ? "score-tick pass" : "score-tick"}
                style={{ left: `${t}%` }} />
        ))}
      </div>
      {!compact && (
        <div className="score-caption">
          {fmt(score)} из 100 · {left > 0 ? `до зачёта ${fmt(left)}` : "порог зачёта пройден"}
        </div>
      )}
    </div>
  );
}

/** Вторая строка карточки/строки: семестр · оценка словом · ECTS · баллы. */
export function gradeMeta(g: Grade, semester: string): string {
  const parts = [`${semester} семестр`];
  if (g.status === "in_progress") {
    parts.push("семестр идёт");
  } else {
    if (g.five !== null && g.label) parts.push(g.label);
    if (g.ects_letter) parts.push(`ECTS ${g.ects_letter}`);
    if (g.score !== null) parts.push(`баллы: ${fmt(g.score)}`);
    if (g.status === "provisional") parts.push("предварительно");
  }
  return parts.join(" · ");
}

/** Официальная шкала; подсвечены строки, куда попали оценки студента. */
export function ScaleTable({ grades }: { grades: Grade[] }) {
  const [bands, setBands] = useState<ScaleBand[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    api.gradingScale().then(setBands).catch(() => setError(true));
  }, []);
  if (error) return <p className="error">Не удалось загрузить шкалу.</p>;
  if (!bands) return <p className="meta">Загрузка…</p>;

  const scored = grades.filter((g) => g.status === "final" && g.score !== null);
  const count = (b: ScaleBand) =>
    scored.filter((g) => Math.floor(g.score!) >= b.lo && Math.floor(g.score!) <= b.hi).length;

  return (
    <div className="scale">
      <p className="meta">
        Итоговая оценка выставляется по 100-балльной сумме. Подсвечены строки,
        в которые попали ваши оценки, цифра — сколько их.
      </p>
      <div className="scale-scroll">
        <table className="scale-table">
          <thead>
            <tr>
              <th>Баллы</th>
              <th>Традиционная</th>
              <th>Бинарная</th>
              <th>ECTS</th>
            </tr>
          </thead>
          <tbody>
            {bands.map((b) => {
              const n = count(b);
              return (
                <tr key={b.ects} className={n > 0 ? "hit" : undefined}>
                  <td className="nowrap">
                    {b.lo}–{b.hi}
                    {n > 0 && (
                      <span className="scale-count" title="Ваших оценок в этой строке">
                        {n}
                      </span>
                    )}
                  </td>
                  <td>{b.traditional}</td>
                  <td>{b.passed ? "Зачтено" : "Не зачтено"}</td>
                  <td>
                    <strong>{b.ects}</strong>
                    <div className="scale-sub">{b.passed ? "passed" : "failed"}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="meta">
        ⚠ — значение в ведомости расходится со шкалой (показано как в ведомости).
        «≈» — предварительная оценка по баллам: в ведомости её ещё нет.
      </p>
    </div>
  );
}
