/** Описание предмета из Figma-макета: абзац + списки «Чему вы научитесь» /
 *  «Содержание …». Обычный текст, а не disabled-textarea: та рисовала
 *  описание серым и выглядела как недоступное поле.
 *  Пустое описание — текст-заглушка. */

import { Stack, Text } from "@atlaskit/primitives/compiled";
import type { SubjectDescription } from "../api";

export function hasDescription(d: SubjectDescription | null | undefined): boolean {
  return Boolean(
    d && (d.about || (d.skills ?? []).length > 0 || (d.content ?? []).length > 0)
  );
}

function Section({ title, items }: { title: string | null; items: string[] }) {
  if (!title || items.length === 0) return null;
  return (
    <div>
      <div className="detail-label">{title.replace(/:\s*$/, "")}</div>
      <ul className="description-list">
        {items.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  );
}

export default function SubjectDescriptionView({
  description,
}: {
  description: SubjectDescription | null | undefined;
}) {
  if (!hasDescription(description)) {
    return (
      <Stack space="space.100">
        <Text>Информация о предмете недоступна.</Text>
        <Text color="color.text.subtle">
          Для просмотра подробной информации обратитесь к преподавателю или
          в учебный отдел.
        </Text>
      </Stack>
    );
  }
  const d = description!;
  return (
    <section className="description" aria-label="Описание дисциплины">
      <div className="detail-label">Описание дисциплины</div>
      {d.about && <p className="description-about">{d.about}</p>}
      <Section title={d.skills_title} items={d.skills ?? []} />
      <Section title={d.content_title} items={d.content ?? []} />
    </section>
  );
}
