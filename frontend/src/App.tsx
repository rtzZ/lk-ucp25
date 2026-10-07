/** Корень: вход -> вкладки «Расписание» / «Оценки». */

import { useEffect, useState } from "react";
import Button from "@atlaskit/button/new";
import IconButton from "@atlaskit/button/icon/button";
import ThemeIcon from "@atlaskit/icon/core/theme";
import Grades from "./screens/Grades";
import Login from "./screens/Login";
import Schedule from "./screens/Schedule";
import {
  api,
  session,
  setUnauthorizedHandler,
  UnauthorizedError,
  type Student,
} from "./api";
import {
  applyTheme,
  cycleTheme,
  saveTheme,
  storedTheme,
  themeNextLabel,
  type ThemeMode,
} from "./theme";
import "./styles.css";

// Старые ключи (вход без пароля) — больше не используются.
for (const key of ["lk-student", "lk-group"]) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* storage недоступен */
  }
}

export default function App() {
  const [student, setStudent] = useState<Student | null>(null);
  // checking — сверяем сохранённый токен; offline — сервер недоступен.
  const [status, setStatus] = useState<"checking" | "ready" | "offline">(
    () => (session.get() ? "checking" : "ready")
  );
  const [tab, setTab] = useState<"schedule" | "grades">("schedule");
  const [theme, setTheme] = useState<ThemeMode>(storedTheme);

  const restore = () => {
    if (!session.get()) {
      setStatus("ready");
      return;
    }
    setStatus("checking");
    api
      .me()
      .then((s) => {
        setStudent(s);
        setStatus("ready");
      })
      .catch((e) => {
        // 401 уже обработан (токен сброшен) — экран входа.
        setStatus(e instanceof UnauthorizedError ? "ready" : "offline");
      });
  };

  useEffect(() => {
    // Любой 401 (токен истёк/отозван) — на экран входа.
    setUnauthorizedHandler(() => {
      session.clear();
      setStudent(null);
    });
    restore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    saveTheme(theme);
    void applyTheme(theme);
  }, [theme]);

  const login = (s: Student) => {
    setStudent(s);
    setTab("schedule");
  };

  const logout = () => {
    void api.logout().catch(() => {});
    setStudent(null);
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

  if (status !== "ready") {
    return (
      <main className="page">
        <div className="theme-toggle-row">{themeButton}</div>
        {status === "checking" ? (
          <p className="meta">Загрузка…</p>
        ) : (
          <div className="card">
            <p className="error">Нет связи с сервером. Проверьте соединение.</p>
            <div className="actions">
              <Button onClick={restore}>Повторить</Button>
            </div>
          </div>
        )}
      </main>
    );
  }

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
            <div className="meta">{student.group}</div>
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
      {tab === "schedule" ? <Schedule group={student.group} /> : <Grades student={student} />}
    </main>
  );
}
