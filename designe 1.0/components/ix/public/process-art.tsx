import {Database, Fingerprint, ScanLine, ArrowDown, Check} from 'lucide-react';

/** Decorative explanation; no account data or connection status. */
export function ProcessArt() {
  return <figure className="ix-process-art" aria-label="От источника к проверяемому решению">
    <figcaption>ПУТЬ ОДНОГО РЕШЕНИЯ</figcaption>
    <div className="ix-process-art-card"><Database aria-hidden="true"/><div><small>01 / ИСТОЧНИКИ</small><strong>Данные с контекстом</strong><p>Директ · Метрика · выбранный период</p></div></div>
    <ArrowDown className="ix-process-art-arrow" aria-hidden="true"/>
    <div className="ix-process-art-card"><ScanLine aria-hidden="true"/><div><small>02 / ОСНОВАНИЕ</small><strong>Каждый вывод проверяем</strong><p>Расчёт · достаточность · ограничения</p><div className="ix-process-art-bars" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/></div></div></div>
    <ArrowDown className="ix-process-art-arrow" aria-hidden="true"/>
    <div className="ix-process-art-card"><Fingerprint aria-hidden="true"/><div><small>03 / ВАШЕ РЕШЕНИЕ</small><strong>Контроль остаётся у вас</strong><p><Check size={14} aria-hidden="true"/> Ручное действие и проверка результата</p></div></div>
    <p className="ix-process-art-note">Схема процесса · не статус подключения</p>
  </figure>;
}
