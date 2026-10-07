/** Экран входа: ФИО -> временный пароль от Telegram-бота -> вход. */

import { useEffect, useState, type ReactNode } from "react";
import Button, { LinkButton } from "@atlaskit/button/new";
import SendIcon from "@atlaskit/icon/core/send";
import Textfield from "@atlaskit/textfield";
import { api, type AuthConfig, type Student } from "../api";

interface Props {
  onLogin: (s: Student) => void;
  /** Кнопка темы — в шапке карточки, а не отдельно над ней. */
  headerAction?: ReactNode;
}

const NO_CONNECTION = "Нет связи с сервером. Проверьте соединение.";

export default function Login({ onLogin, headerAction }: Props) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"name" | "password">("name");
  const [devPassword, setDevPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.authConfig().then(setConfig).catch(() => {});
  }, []);

  const botLink = config?.bot_username
    ? `https://t.me/${config.bot_username}`
    : "";
  const botName = config?.bot_username ? `@${config.bot_username}` : "бота кабинета";

  const message = (e: unknown) =>
    e instanceof TypeError || (e instanceof Error && e.message.startsWith("timeout"))
      ? NO_CONNECTION
      : (e as Error).message;

  const requestPassword = async () => {
    setError("");
    setBusy(true);
    try {
      const r = await api.requestPassword(lastName.trim(), firstName.trim());
      setDevPassword(r.dev_password ?? "");
      setPassword("");
      setStep("password");
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const login = async () => {
    setError("");
    setBusy(true);
    try {
      onLogin(await api.login(lastName.trim(), firstName.trim(), password.trim()));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const nameFilled = lastName.trim() !== "" && firstName.trim() !== "";

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (busy) return;
        void (step === "name" ? requestPassword() : login());
      }}
    >
      <div className="login-top">
        <div>
          <h1>Кабинет студента</h1>
          <div className="meta">
            {config?.group ? `Группа ${config.group} · ` : ""}расписание и оценки
          </div>
        </div>
        {headerAction}
      </div>
      <label htmlFor="last-name">Фамилия</label>
      <Textfield
        id="last-name"
        value={lastName}
        isDisabled={step === "password"}
        onChange={(e) => setLastName((e.target as HTMLInputElement).value)}
        placeholder="Как в ведомости"
        autoComplete="family-name"
      />
      <label htmlFor="first-name">Имя</label>
      <Textfield
        id="first-name"
        value={firstName}
        isDisabled={step === "password"}
        onChange={(e) => setFirstName((e.target as HTMLInputElement).value)}
        placeholder="Без отчества"
        autoComplete="given-name"
      />

      {step === "name" ? (
        <>
          <div className="actions">
            <Button appearance="primary" type="submit" isDisabled={!nameFilled || busy}>
              Получить пароль
            </Button>
          </div>
          <p className="meta">
            Пароль придёт от {botName} в Telegram. Первый раз? Напишите боту
            /start и укажите фамилию и имя.
          </p>
          {botLink && (
            <LinkButton
              href={botLink}
              target="_blank"
              rel="noopener noreferrer"
              iconBefore={SendIcon}
              shouldFitContainer
            >
              Открыть {botName}
            </LinkButton>
          )}
        </>
      ) : (
        <>
          <p className="meta">
            Если ваш Telegram привязан, пароль уже отправлен от{" "}
            {botLink ? <a href={botLink} target="_blank" rel="noreferrer">{botName}</a> : botName}.
            Пароль действует 1 минуту. Не пришёл — напишите боту /start.
          </p>
          {devPassword && (
            <p className="meta">Режим разработки: пароль {devPassword}</p>
          )}
          <label htmlFor="password">Пароль из Telegram</label>
          <Textfield
            id="password"
            value={password}
            autoFocus
            autoComplete="one-time-code"
            inputMode="numeric"
            onChange={(e) => setPassword((e.target as HTMLInputElement).value)}
            placeholder="6 цифр"
          />
          <div className="actions login-buttons">
            <Button appearance="primary" type="submit" isDisabled={!password.trim() || busy}>
              Войти
            </Button>
            <Button
              appearance="subtle"
              onClick={() => {
                setStep("name");
                setError("");
              }}
            >
              Изменить ФИО
            </Button>
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
