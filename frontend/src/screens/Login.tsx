/** Экран входа: группа + фамилия/имя. */

import { useEffect, useState } from "react";
import Button from "@atlaskit/button/new";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { api, type Student } from "../api";

interface Props {
  onLogin: (s: Student, group: string) => void;
}

export default function Login({ onLogin }: Props) {
  const [groups, setGroups] = useState<string[]>(["УЦП-25"]);
  const [group, setGroup] = useState("УЦП-25");
  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<Student[]>([]);

  useEffect(() => {
    api.groups().then((g) => {
      if (g.length > 0) {
        setGroups(g);
        setGroup(g[0]);
      }
    }).catch(() => {});
  }, []);

  const submit = async () => {
    setError("");
    setSuggestions([]);
    try {
      const student = await api.login(lastName.trim(), firstName.trim());
      onLogin(student, group);
    } catch (e) {
      const sug = (e as { suggestions?: Student[] }).suggestions ?? [];
      setSuggestions(sug);
      setError(
        sug.length > 0 ? "Уточните имя:" : "Студент не найден. Проверьте фамилию."
      );
    }
  };

  return (
    <div className="card">
      <h1>Кабинет студента</h1>
      <label>Группа</label>
      <Select
        inputId="group-select"
        options={groups.map((g) => ({ label: g, value: g }))}
        value={{ label: group, value: group }}
        onChange={(o) => o && setGroup(o.value)}
      />
      <label htmlFor="last-name">Фамилия</label>
      <Textfield
        id="last-name"
        value={lastName}
        onChange={(e) => setLastName((e.target as HTMLInputElement).value)}
        placeholder="Иванов"
      />
      <label htmlFor="first-name">Имя</label>
      <Textfield
        id="first-name"
        value={firstName}
        onChange={(e) => setFirstName((e.target as HTMLInputElement).value)}
        placeholder="Иван"
      />
      <div className="actions">
        <Button appearance="primary" onClick={submit} isDisabled={!lastName.trim()}>
          Войти
        </Button>
      </div>
      {error && <p className="error">{error}</p>}
      {suggestions.map((s) => (
        <div key={s.id} className="actions">
          <Button appearance="subtle" onClick={() => onLogin(s, group)}>
            {s.full_name || `${s.last_name} ${s.first_name}`}
          </Button>
        </div>
      ))}
    </div>
  );
}
