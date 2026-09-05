/** Корень: вход -> вкладки «Расписание» / «Оценки». */

import { useState } from "react";
import Button from "@atlaskit/button/new";
import Grades from "./screens/Grades";
import Login from "./screens/Login";
import Schedule from "./screens/Schedule";
import type { Student } from "./api";
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

  const login = (s: Student, g: string) => {
    setStudent(s);
    setGroup(g);
    localStorage.setItem("lk-student", JSON.stringify(s));
    localStorage.setItem("lk-group", g);
  };

  const logout = () => {
    setStudent(null);
    localStorage.removeItem("lk-student");
  };

  if (!student) {
    return (
      <main className="page">
        <Login onLogin={login} />
      </main>
    );
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <strong>{student.full_name || `${student.last_name} ${student.first_name}`}</strong>
          <div className="meta">{group}</div>
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
      {tab === "schedule" ? <Schedule group={group} /> : <Grades student={student} />}
    </main>
  );
}
