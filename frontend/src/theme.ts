/** Переключение темы (светлая/тёмная/авто) через @atlaskit/tokens.
 *
 * Режимы и цикл — как на www.pomidoruspekha.ru:
 * light -> dark -> auto -> light.
 */

import { setGlobalTheme } from "@atlaskit/tokens/set-global-theme";

export type ThemeMode = "light" | "dark" | "auto";

const STORAGE_KEY = "lk-theme";

/** Начальная тема: сохранённый выбор, иначе — из системных настроек. */
export function storedTheme(): ThemeMode {
  const v = localStorage.getItem(STORAGE_KEY);
  if (v === "light" || v === "dark" || v === "auto") return v;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function saveTheme(mode: ThemeMode): void {
  localStorage.setItem(STORAGE_KEY, mode);
}

/** Применяет тему глобально: ставит data-color-mode на <html> и грузит CSS.
 * «Авто» резолвится в текущую системную тему в момент применения. */
export async function applyTheme(mode: ThemeMode): Promise<void> {
  const resolved: "light" | "dark" =
    mode === "auto"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : mode;
  await setGlobalTheme({ colorMode: resolved });
}

/** Следующий режим в цикле light -> dark -> auto -> light. */
export function cycleTheme(mode: ThemeMode): ThemeMode {
  return mode === "light" ? "dark" : mode === "dark" ? "auto" : "light";
}

/** Подпись для тултипа кнопки: какой режим станет активным после клика. */
export const themeNextLabel: Record<ThemeMode, string> = {
  light: "Тёмная",
  dark: "Авто",
  auto: "Светлая",
};