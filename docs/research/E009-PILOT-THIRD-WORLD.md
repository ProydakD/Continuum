# E009 — третий завершённый пилотный мир (537)

2026-10-24. Промежуточный отчёт по назначениям 021–030, не итог исследования.

| Назначение | Условие | Трек | A–E технически | BRI | Natural opportunities |
|---|---|---|---|---:|---:|
|pilot-021|F0|controlled|да|1|—|
|pilot-022|S0|controlled|да|1|—|
|pilot-023|F1|controlled|да|1|—|
|pilot-024|FULL-JOURNAL|natural|нет|—|неизвестно|
|pilot-025|F1|natural|да|—|0|
|pilot-026|F0|natural|да|—|0|
|pilot-027|FULL-JOURNAL|controlled|да|0|—|
|pilot-028|S1|natural|да|—|0|
|pilot-029|S0|natural|да|—|0|
|pilot-030|S1|controlled|да|1|—|

## Сопоставимость и controlled-результаты

Все десять назначений использовали protocol 3 и execution binding amendment 004:
`96c3b0290ee89ca15022c18d5fda5298cff27d5ce1b397d88f807270022597cf`.
Модель, инструкции, код, evaluator, порядок и бюджеты серии не менялись.
Назначения не повторялись, отрицательные исходы не исключались.

Технически завершены 9/10 цепочек. Controlled BRI=1 у 4/5; F0, S0, F1 и S1
прошли все gates T/R/D/A/N/P/Q. У всех пяти controlled-цепочек правильный новый
ответ и 0/16 preservation losses. Эти показатели сами по себе не равны BRI.

**pilot-027, FULL-JOURNAL:** не пройден только gate A в checkpoint B. Для I, J и K
сохранены верные статусы `supported`, но `bases=[["e:EA","e:EB","e:EC"]]`
не содержит отдельного альтернативного основания `["e:EA"]`, обязательного
для зарегистрированных независимых утверждений. В A/C/D отдельное EA присутствует.
Остальные gates, включая soundness/provenance, пройдены. Это нарушение критерия
явного сохранения независимого основания, не наблюдаемая потеря утверждений,
не неверный новый ответ и не доказательство внутреннего забывания модели.

Во втором мире FULL-JOURNAL имел BRI=1, а F0/S0/S1 — BRI=0; здесь картина иная.
Два мира под одним binding показывают вариативность наблюдаемых исходов, но
не устанавливают превосходство условия, эффект размера памяти или проверки.
Первый мир со смешанными версиями не объединяется с ними как однородная серия.

## Отказ публикации pilot-024

FULL-JOURNAL/natural остановился на A: `failed`, затем четыре `upstream_missing`.
В исходных инструкциях прямо указано:
`published_memory={format:F,payload:<nonempty free text>} for F/C0/FULL-JOURNAL,`.

1. Первая публикация содержит `format="FULL-JOURNAL"`; frozen broker отклоняет
   её с `ValueError: assigned memory representation required`.
2. Вторая публикация повторяет это значение и получает то же отклонение.
3. Третья использует `format="F"`, но две допустимые попытки уже исчерпаны:
   `PermissionError: invalid publication transition`.

Наблюдаемые tool-ответы во всех трёх случаях — `{"error":"capability_rejected"}`.
Модель завершила A JSON-ответом `publication_failed`; публикации в MCP нет.
Диагностика воспроизвела соответствующие guards на исходных аргументах без
записи, транспорта или новых API-запросов. Независимый replay сохранил отказ,
а не превратил error-final в успешный результат. Все 45 raw files неизменны.
Это отказ при выполнении публичного контракта, не наблюдавшийся outage провайдера.

## Natural-трек и достаточность opportunities

Четыре завершённые natural-цепочки имеют валидную provenance/history/evidence
на A–D и opportunities=0. У pilot-024 знаменатель неизвестен из-за отсутствия
предшествующей публикации. Во всех пяти revision rate неопределена.

В завершённых цепочках сформировано 2–5 корней на переход; у pilot-029 (S0)
два корня имеют зависимости на каждом B/C/D, но opportunities всё равно 0.
Preservation losses: 0/12 (F1), 0/9 (F0), 0/11 (S1), 0/16 (S0).
Неизвестный знаменатель failed-цепочки не заменяется нулём, а отсутствие
opportunities не засчитывается как успешный dependency repair.

Накопленные пилотные данные пока не дают оценить natural revision rate.
Остальные заранее назначенные calibration worlds продолжаются без добавления
зависимостей постфактум или ослабления evaluator. После полного пилота нужна
оценка достаточности этого endpoint, а не вывод об успешном repair из нулей.

## Проверки и расходы

Независимо проверены 1344 raw files; сохранённые analysis совпали полностью.
Только назначения 021–030: 181 transport attempts, 734823 reported input и
121585 output tokens, unknown usage у 0 попыток. Денежная стоимость неизвестна;
availability и отдельные diagnostics исключены. При анализе новых API-вызовов нет.

Артефакты: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e009-001\pilot-progress-003`.
Данные: THIRD-WORLD.json, THIRD-WORLD.csv, aggregate_third_world.py,
aggregate-command.json; диагнозы: PILOT-024-PUBLICATION-AUDIT-v2.json,
PILOT-027-CLAIM-AUDIT.json, PILOT-027-INDEPENDENCE-AUDIT.json.
Первый audit 024 и его stdout сохранены; v2 исправляет только название поля
хеша полного запроса на `first_request_sha256`, не данные или исход эксперимента.

Тот же driver начал 031 и продолжает исходную серию до 120. Полный пилот,
две независимо изолированные T2-линии, финальная предрегистрация/power/N,
held-out, robustness, независимый анализ и полный отчёт ещё не завершены.
