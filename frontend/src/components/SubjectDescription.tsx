/** Описание предмета из Figma-макета в textarea-компоненте ADS
 *  (`@atlaskit/textarea`, readonly): заголовки-подсписки «Чему вы научитесь» /
 *  «Содержание …» схлопываются в единый текст с маркерами «•».
 *  Высота textarea ставится по `scrollHeight` (ResizeObserver + шрифты),
 *  `overflow: hidden` — скроллбара нет ни в одном браузере.
 *  Пустое описание — текст-заглушка вместо textarea. */

import { Label } from "@atlaskit/form";
import { Stack, Text } from "@atlaskit/primitives/compiled";
import TextArea from "@atlaskit/textarea";
import { useLayoutEffect, useRef } from "react";
import type { SubjectDescription } from "../api";

export function hasDescription(d: SubjectDescription | null | undefined): boolean {
  return Boolean(
    d && (d.about || (d.skills ?? []).length > 0 || (d.content ?? []).length > 0)
  );
}

/** Схлопывает описание в plain-текст для textarea. */
function descriptionValue(d: SubjectDescription): string {
  const parts: string[] = [];
  if (d.about) parts.push(d.about);
  if (d.skills_title && d.skills.length > 0) {
    parts.push(`${d.skills_title}:\n${d.skills.map((s) => `• ${s}`).join("\n")}`);
  }
  if (d.content_title && d.content.length > 0) {
    parts.push(
      `${d.content_title}:\n${d.content.map((s) => `• ${s}`).join("\n")}`
    );
  }
  return parts.join("\n\n");
}

export default function DescriptionTextArea({
  description,
}: {
  description: SubjectDescription | null | undefined;
}) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const el = taRef.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "auto";
      el.style.minHeight = `${el.scrollHeight}px`;
    };
    fit();
    document.fonts?.ready.then(fit).catch(() => undefined);
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [description]);

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
  return (
    <Stack space="space.050">
      <Label htmlFor="lesson-description">Описание дисциплины</Label>
      <TextArea
        ref={taRef}
        id="lesson-description"
        value={descriptionValue(description!)}
        isDisabled
        resize="none"
        minimumRows={4}
        maxHeight="none"
        appearance="subtle"
        style={{ overflow: "hidden" }}
      />
    </Stack>
  );
}