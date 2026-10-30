import {CalendarDays} from 'lucide-react';

export function PeriodPicker({days, period}: {days: string; period: {from: string; to: string}}) {
  return <fieldset className="ix-period-picker"><legend><CalendarDays size={17} aria-hidden/>Период анализа · МСК</legend>
    <span className="ix-period-dates"><time dateTime={period.from}>{period.from}</time><span aria-hidden> → </span><time dateTime={period.to}>{period.to}</time></span>
    <div>{['7', '30'].map(value => <label key={value}><input type="radio" name="days" value={value} defaultChecked={days === value}/><span>{value} дней</span></label>)}</div>
    <small>Загруженный период. Выберите длительность и нажмите «Показать».</small>
  </fieldset>;
}
