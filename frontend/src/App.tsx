/** Корень: вход -> вкладки «Расписание» / «Оценки». */

import { useEffect, useState } from "react";
import Button from "@atlaskit/button/new";
import IconButton from "@atlaskit/button/icon/button";
import ThemeIcon from "@atlaskit/icon/core/theme";
import Grades from "./screens/Grades";
import Login from "./screens/Login";
import Schedule from "./screens/Schedule";
import { api, type Student } from "./api";
import {
  applyTheme,
  cycleTheme,
  saveTheme,
  storedTheme,
  themeNextLabel,
  type ThemeMode,
} from "./theme";
import "./styles.css";

export default function App() {
  const [student, setStudent] = useState<Student | null>(() => {
    try {
      const raw = localStorage.getItem("lk-student");
      return raw ? (JSON.parse(raw) as Student) : null;
    } catch {
      return null;
    }
  });
  const [group, setGroup] = useState(
    () => localStorage.getItem("lk-group") ?? "УЦП-25"
  );
  const [tab, setTab] = useState<"schedule" | "grades">("schedule");
  const [theme, setTheme] = useState<ThemeMode>(storedTheme);
  // Студент из localStorage не проверен: его id мог устареть после
  // синхронизации, поэтому оценки грузим только после сверки по code.
  const [verified, setVerified] = useState(false);

  useEffect(() => {
    if (!student) return;
    let cancelled = false;
    api
      .studentByCode(student.code)
      .then((fresh) => {
        if (cancelled) return;
        if (fresh === null) {
          logout(); // студента больше нет в ведомости
          return;
        }
        setStudent(fresh);
        localStorage.setItem("lk-student", JSON.stringify(fresh));
        setVerified(true);
      })
      .catch(() => {
        // Нет связи — показываем сохранённое; Grades сам покажет ошибку.
        if (!cancelled) setVerified(true);
      });
    return () => {
      cancelled = true;
    };
    // Сверка только при старте; после входа данные свежие.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    saveTheme(theme);
    void applyTheme(theme);
  }, [theme]);

  const login = (s: Student, g: string) => {
    setStudent(s);
    setVerified(true);
    setGroup(g);
    localStorage.setItem("lk-student", JSON.stringify(s));
    localStorage.setItem("lk-group", g);
  };

  const logout = () => {
    setStudent(null);
    localStorage.removeItem("lk-student");
  };

  const themeButton = (
    <IconButton
      appearance="subtle"
      spacing="compact"
      icon={ThemeIcon}
      label={`Переключить тему (сейчас: ${themeNextLabel[theme]})`}
      onClick={() => setTheme(cycleTheme(theme))}
    />
  );

  if (!student) {
    return (
      <main className="page">
        <div className="theme-toggle-row">{themeButton}</div>
        <Login onLogin={login} />
      </main>
    );
  }

  return (
    <main className="page">
      <header className="topbar">
        <div className="identity">
          {themeButton}
          <div>
            <strong>{student.full_name || `${student.last_name} ${student.first_name}`}</strong>
            <div className="meta">{group}</div>
          </div>
        </div>
        <Button appearance="subtle" onClick={logout}>
          Выйти
        </Button>
      </header>
      <nav className="tabs">
        <button
          className={tab === "schedule" ? "chip active" : "chip"}
          onClick={() => setTab("schedule")}
        >
          Расписание
        </button>
        <button
          className={tab === "grades" ? "chip active" : "chip"}
          onClick={() => setTab("grades")}
        >
          Оценки
        </button>
      </nav>
      {tab === "schedule" ? (
        <Schedule group={group} />
      ) : verified ? (
        <Grades student={student} />
      ) : (
        <p className="meta">Загрузка…</p>
      )}
    </main>
  );
}
