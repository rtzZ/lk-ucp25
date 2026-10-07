/** E2E: вход -> расписание -> оценки (desktop + mobile).
 *
 * Запуск: backend с демо-данными и dev-паролями + frontend dev-сервер, затем:
 *   DATABASE_URL=sqlite+aiosqlite:///./lk-dev.db SEED_DEMO=1 AUTH_DEV_MODE=1 \
 *     uvicorn app.main:app --port 8001   # из backend/
 *   npm run dev                            # из frontend/ (VITE_API_URL=http://localhost:8001)
 *   npx playwright test                    # из frontend/
 */
import { expect, test } from "@playwright/test";

/** Пароль из ответа /auth/request_password (AUTH_DEV_MODE=1 вместо Telegram). */
async function requestPassword(page: import("@playwright/test").Page): Promise<string> {
  await page.getByRole("textbox", { name: "Фамилия" }).fill("Иванов");
  await page.getByRole("textbox", { name: "Имя" }).fill("Иван");
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/auth/request_password")),
    page.getByRole("button", { name: "Получить пароль" }).click(),
  ]);
  const body = (await resp.json()) as { dev_password: string | null };
  expect(body.dev_password, "backend должен работать с AUTH_DEV_MODE=1").toBeTruthy();
  return body.dev_password!;
}

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  const password = await requestPassword(page);
  await page.getByRole("textbox", { name: "Пароль из Telegram" }).fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Иванов Иван Иванович").first()).toBeVisible();
}

async function showAll(page: import("@playwright/test").Page) {
  // Тогл по умолчанию «Актуальное», сид-даты в прошлом — показываем всё.
  await page.locator(".toggle-row").click({ force: true });
}

test("вход и просмотр расписания", async ({ page }) => {
  await login(page);
  // по умолчанию «Актуальное»: сид-даты прошли — пусто
  await expect(page.getByText("Нет записей.")).toBeVisible();
  await showAll(page);
  await expect(
    page.getByRole("heading", { name: /понедельник, 9 февраля/ })
  ).toBeVisible();
  await expect(page.getByText("Математика").first()).toBeVisible();
});

test("вкладка оценок", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Оценки" }).click();
  await expect(page.getByText("Средний балл: 5.00")).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Математика" })
  ).toBeVisible();
});

test("сортировка и фильтр прямо в шапке оценок", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Оценки" }).click();
  // сортировка по предмету: 1-й клик -> ASC (Математика), 2-й -> DESC (Физика)
  await page.getByRole("button", { name: "Сортировка: Предмет" }).click();
  let cells = await page.getByRole("cell").allTextContents();
  expect(cells[0]).toContain("Математика");
  await page.getByRole("button", { name: "Сортировка: Предмет" }).click();
  cells = await page.getByRole("cell").allTextContents();
  expect(cells[0]).toContain("Физика");
  // фильтр-чекбокс в шапке «Оценка» -> только Математика
  await page.getByRole("button", { name: "Фильтр: Оценка" }).click();
  await page.getByRole("option", { name: "5" }).click();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("cell", { name: "Математика" })
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Физика" })
  ).toHaveCount(0);
  // «Очистить всё» возвращает обе строки
  await page.getByRole("button", { name: "Фильтр: Оценка" }).click();
  await page.getByRole("option", { name: "Очистить всё" }).click();
  await expect(
    page.getByRole("cell", { name: "Физика" })
  ).toBeVisible();
});
test("drawer занятия со ссылкой на подключение", async ({ page }) => {
  await login(page);
  await showAll(page);
  await page.getByRole("button", { name: /Математика/ }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Сидоров");
  // действия — секция из двух пунктов: ссылка и календарь
  await expect(
    page.getByRole("dialog").getByRole("link", { name: "Подключиться к паре" })
  ).toHaveAttribute("href", "https://video.example.com/math-1");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // пара без ссылки — кнопка disabled + скачивание .ics
  await page.getByRole("button", { name: /Физика/ }).first().click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Подключиться к паре" })
  ).toBeDisabled();
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("dialog").getByRole("button", { name: "Добавить в календарь" }).click(),
  ]);
  expect(dl.suggestedFilename()).toBe("raspisanie.ics");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("drawer предмета в таблице оценок", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Оценки" }).click();
  await page.getByRole("cell", { name: "Математика" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Математика");
  // Математики нет в Figma-макете — показывается заглушка
  await expect(page.getByRole("dialog")).toContainText(
    "Информация о предмете недоступна."
  );
  await page.getByRole("dialog").getByRole("button", { name: "Close drawer" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("неверный пароль — ошибка, без входа", async ({ page }) => {
  await page.goto("/");
  const password = await requestPassword(page);
  const wrong = password === "000000" ? "111111" : "000000";
  await page.getByRole("textbox", { name: "Пароль из Telegram" }).fill(wrong);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Неверный или истёкший пароль")).toBeVisible();
  await expect(page.getByRole("button", { name: "Выйти" })).toHaveCount(0);
});

test("сессия переживает перезагрузку, выход её отзывает", async ({ page }) => {
  await login(page);
  await page.reload();
  await expect(page.getByText("Иванов Иван Иванович").first()).toBeVisible();
  const token = await page.evaluate(() => localStorage.getItem("lk-token"));
  await page.getByRole("button", { name: "Выйти" }).click();
  await expect(page.getByRole("textbox", { name: "Фамилия" })).toBeVisible();
  // отозванный токен на сервере больше не работает
  await page.evaluate((t) => localStorage.setItem("lk-token", t!), token);
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Фамилия" })).toBeVisible();
});

test("без токена данные не отдаются", async ({ request }) => {
  const api = "http://localhost:8001";
  for (const path of ["/grades", "/schedule", "/auth/me"]) {
    expect((await request.get(api + path)).status()).toBe(401);
  }
});

test.describe("телефон 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("мобильный вход и расписание без горизонтального скролла", async ({
    page,
  }) => {
    await login(page);
    await showAll(page);
    await expect(page.getByText("Физика").first()).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBe(0);
  });

  test("оценки карточками: без скролла вбок, фильтр и drawer работают", async ({
    page,
  }) => {
    await login(page);
    await page.getByRole("button", { name: "Оценки" }).click();
    const cards = page.getByRole("list", { name: "Оценки" }).getByRole("listitem");
    await expect(cards).toHaveCount(2);
    await expect(page.getByRole("table")).toHaveCount(0);
    await expect(cards.filter({ hasText: "Математика" })).toContainText("5 · Отлично");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBe(0);
    // фильтр по оценке из строки над карточками
    await page.getByRole("button", { name: "Фильтр: Оценка" }).click();
    await page.getByRole("option", { name: "5" }).click();
    await page.keyboard.press("Escape");
    await expect(cards).toHaveCount(1);
    // карточка открывает drawer предмета
    await cards.first().getByRole("button", { name: "Математика" }).click();
    await expect(page.getByRole("dialog")).toContainText("Математика");
  });
});
