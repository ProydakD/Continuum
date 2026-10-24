# E009 — первый завершённый pilot-world321

2026-10-24. Промежуточное эмпирическое наблюдение, не итог исследования.

| Назначение | Условие | Трек | Протокол | A–E технически | BRI | Natural opportunities |
|---|---|---|---:|---|---:|---:|
|pilot-001|F1|natural|1|нет|—|—|
|pilot-002|F0|controlled|2|нет|0|—|
|pilot-003|S0|controlled|2|нет|0|—|
|pilot-004|S0|natural|2|нет|—|—|
|pilot-005|F1|controlled|2|да|0|—|
|pilot-006|S1|natural|2|да|—|0|
|pilot-007|F0|natural|3|да|—|0|
|pilot-008|FULL-JOURNAL|natural|3|нет|—|—|
|pilot-009|FULL-JOURNAL|controlled|3|да|1|—|
|pilot-010|S1|controlled|3|да|1|—|

## Что измерено

BRI — произведение всех зарегистрированных gates T/R/D/A/N/P/Q: четыре
snapshot A–D и новый вопрос E. Успешная техническая передача или правильный
новый ответ отдельно не считаются полным belief revision.

- pilot-009 FULL-JOURNAL: BRI=1, все gates пройдены; preservation worst-case losses 0/12; максимальный read envelope 9501 bytes.
- pilot-010 S1: BRI=1, все gates пройдены; preservation worst-case losses 0/12; максимальный read envelope 4241 bytes.

Все пять условий и оба трека первого мира имеют учтённый исход. Прежние
тайм-ауты, ошибка формата публикации008 и BRI0 у005 не заменены успешными
повторениями. Старые raw и score/trace сохранены; пилот001 дополнительно
сопоставлен с родительским replay из-за прежнего добавления metadata tool_calls.

## Ограничения и следующий шаг

В мире смешаны protocol1/2/3 и разные deadline amendments. Поэтому нельзя
вычислять причинный эффект F/S или V1 по различиям этой таблицы. Положительный
BRI одной цепочки показывает наблюдённое выполнение данного задания, а не
обобщённую способность, превосходство условия или коллективный интеллект.

Отсутствие natural opportunities означает неопределённую revision rate, не
успешный repair. Технические отказы с неизвестным знаменателем также не
подменяются нулевыми opportunities. Нужны остальные calibration worlds и
оценка распределений по условиям/версиям; менять evaluator под эти исходы нельзя.

Продолжение — оставшиеся110 заранее назначенных цепочек pilot011–120 в том же
порядке под amendment004; все исходы, лимиты, stop rules и независимый raw replay
сохраняются. Окончательная предрегистрация/N, обе T2-линии, heldout, robustness
и полный научный отчёт остаются незавершёнными.

## Воспроизводимость и расходы

953 raw files проверены при независимом пересчёте; новых API-запросов при анализе0.
Только десять назначений: 136 transport attempts,
453362 reported input и77426 output tokens;
unknown usage у15 попыток. Неизвестное потребление не равно нулю;
денежная стоимость неизвестна. Availability и отдельные diagnostics исключены.

Артефакты: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e009-001\pilot-progress-001`.
FIRST-WORLD.json, FIRST-WORLD.csv и aggregate_first_world.py; raw и immutable
receipts остаются в соседнем pilot-001.
