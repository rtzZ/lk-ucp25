/** Экран входа: группа + фамилия/имя или Telegram username + код. */

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
  const [telegramUsername, setTelegramUsername] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<Student[]>([]);
  const [codeSent, setCodeSent] = useState(false);

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

  const requestTelegramCode = async () => {
    setError("");
    try {
      const data = await api.telegramRequestCode(telegramUsername.trim());
      if (data.code_sent) {
        setCodeSent(true);
        setError("Код отправлен. Введите его ниже (действует 60 сек).");
      } else {
        setError(data.error || "Ошибка запроса кода");
      }
    } catch (e: any) {
      setError(e.message || "Не удалось отправить код. Проверьте подключение.");
    }
  };

  const telegramLogin = async () => {
    setError("");
    setSuggestions([]);
    try {
      const student = await api.telegramLogin(telegramUsername.trim(), telegramCode.trim());
      onLogin(student, group);
    } catch (e: any) {
      setError(e.message || "Ошибка входа. Проверьте код.");
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
      <div style={{ marginTop: "20px", borderTop: "1px solid #eee", paddingTop: "20px" }}>
        <h3>Вход через Telegram</h3>
        <label htmlFor="telegram-username">Telegram username</label>
        <Textfield
          id="telegram-username"
          value={telegramUsername}
          onChange={(e) => setTelegramUsername((e.target as HTMLInputElement).value)}
          placeholder="@username"
          style={{ marginTop: "8px" }}
        />
        {codeSent && (
          <>
            <label htmlFor="telegram-code">Временный код (6 цифр)</label>
            <Textfield
              id="telegram-code"
              value={telegramCode}
              onChange={(e) => setTelegramCode((e.target as HTMLInputElement).value)}
              placeholder="000000"
              maxLength={6}
              style={{ marginTop: "8px" }}
            />
            <div className="actions" style={{ marginTop: "12px" }}>
              <Button appearance="primary" onClick={telegramLogin} isDisabled={telegramCode.length !== 6}>
                Войти по коду
              </Button>
            </div>
          </>
        )}
        {!codeSent && (
          <div className="actions" style={{ marginTop: "12px" }}>
            <Button appearance="primary" onClick={requestTelegramCode} isDisabled={!telegramUsername.trim()}>
              Получить код
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
