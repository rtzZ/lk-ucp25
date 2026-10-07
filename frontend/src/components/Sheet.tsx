/** Панель подробностей на нативном <dialog>: на телефоне — шторка снизу,
 *  на десктопе — панель справа.
 *
 *  Вместо @atlaskit/drawer: тот всегда выезжает слева, а ширину приходилось
 *  править через хэш CSS-класса библиотеки (ломается при обновлении).
 *  showModal() даёт фокус-ловушку, Esc и затемнение средствами браузера;
 *  клик по затемнению закрывает. */

import { useEffect, useRef, type ReactNode } from "react";
import CrossIcon from "@atlaskit/icon/core/cross";
import IconButton from "@atlaskit/button/icon/button";

interface Props {
  label: string;
  onClose: () => void;
  children: ReactNode;
}

export default function Sheet({ label, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    // Фон под шторкой не скроллится.
    const prev = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = prev;
      if (dialog.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault(); // Esc: закрываем через состояние родителя
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // клик по затемнению
      }}
    >
      <div className="sheet-body">
        <div className="sheet-handle" aria-hidden="true" />
        <div className="sheet-close">
          <IconButton
            appearance="subtle"
            icon={CrossIcon}
            label="Закрыть"
            onClick={onClose}
          />
        </div>
        {children}
      </div>
    </dialog>
  );
}
