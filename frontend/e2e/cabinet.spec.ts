/** E2E: вход -> расписание -> оценки (desktop + mobile).
 *
 * Запуск: backend с демо-данными + frontend dev-сервер, затем:
 *   DATABASE_URL=sqlite+aiosqlite:///./lk-dev.db SEED_DEMO=1 \
 *     uvicorn app.main:app --port 8001   # из backend/
 *   npm run dev                            # из frontend/ (VITE_API_URL=http://localhost:8001)
 *   npx playwright test                    # из frontend/
 */
import { expect, test } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Фамилия" }).fill("Иванов");
  await page.getByRole("textbox", { name: "Имя" }).fill("Иван");
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
    page.getByRole("cell", { name: "Математика (экзамен)" })
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
    page.getByRole("cell", { name: "Математика (экзамен)" })
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Физика (зачет)" })
  ).toHaveCount(0);
  // «Очистить всё» возвращает обе строки
  await page.getByRole("button", { name: "Фильтр: Оценка" }).click();
  await page.getByRole("option", { name: "Очистить всё" }).click();
  await expect(
    page.getByRole("cell", { name: "Физика (зачет)" })
  ).toBeVisible();
});
test("drawer занятия со ссылкой на подключение", async ({ page }) => {
  await login(page);
  await showAll(page);
  await page.getByRole("button", { name: /Математика/ }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Сидоров");
  await expect(
    page.getByRole("link", { name: "Подключиться к паре" })
  ).toHaveAttribute("href", "https://video.example.com/math-1");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // пара без ссылки — красный Lozenge
  await page.getByRole("button", { name: /Физика/ }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Ссылка не указана");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
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

test("drawer предмета в таблице оценок", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Оценки" }).click();
  await page.getByRole("cell", { name: "Математика" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Математика");
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
