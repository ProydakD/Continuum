# E009 — natural provenance и селективность (2026-10-24)

Это проверка evaluator и методики до pilot; **результатов LLM нет**.
Artifact root: `C:/Users/User/Documents/ChatGPT/ContinuumResearch/artifacts/e009-001/natural-001/`.
Основная цель исследования и H1–H6 остаются незавершёнными.

## Найденные ошибки и исправления

Начальный `regression-001-command.json`, exit 1, показал:

| Проверка | До | После |
|---|---:|---:|
| Natural repair с поддельными hash/version/reasons | rate=1 | rate=0 |
| Supported D3 понижен до undetermined | false_retractions=0 | 1 |
| Нет публикации памяти B | technical_complete=true | false |

Тот же вход прошёл после исправления: `regression-002-command.json`.
Дополнительный `typed-001-command.json` выявил принятие bool true вместо integer 1
в новой natural proposition. Теперь тип проверяется буквально; `typed-002`, exit 0.
`empty-001` выявил vacuous post_update_integrity=true при нуле сформированных
гипотез; теперь он null, как и revision rate (`empty-002`, exit 0).
Неуспешные записи сохранены, а не переписаны успешными.

## Реализованная методика

- `e009_guardrails.provenance_valid`: неизменность ID/proposition/origin,
  version+1, точный hash прежней записи, причины только из уже введённых источников;
  изменение статуса связано с текущим add/revoke. Новое утверждение: version=1,
  без предыдущего hash. Удаление старого ID не скрывает историю.
- `natural_opportunities`: знаменатель определяется предшествующей наблюдаемой
  записью, не успешностью текущего ответа. Отсутствующая текущая запись получает
  нулевой credit по известной возможности; неизвестный predecessor не превращается
  в нулевой знаменатель. Полный rate тогда null, известная часть отдельно.
- `score_natural_chain`: condition передаётся из обоих replay; у C0 inherited
  metrics=null. Проверяются формат/наличие публикации, malformed measurement,
  уникальность контекстов, terminal status и обоснование нового ответа.
- Natural post_update_integrity проверяет B–D и E, только при наличии наблюдаемой
  возможности. Поэтому correct B не стирает stale source C или неподтверждённый E.
  Это descriptive проверка, не BRI и не дополнительный confirmatory contrast.
- Controlled BRI остаётся произведением всех ранее определённых gates; дополнен
  отдельным loss/guardrail ledger с фиксированными oracle-supported слотами A–D.
  Понижение, исчезновение и подмена корректного утверждения теперь учитываются.
  Technical failure не исключает назначение: для safety inference используется
  worst-case rate; conditional rate публикуется лишь как дополнительное описание.

Точная семантика draft-004 записана в E009-PREREGISTRATION.json и
E009-HYPOTHESES.md. Это **не final freeze** и не выбор порогов по held-out.

## Наблюдаемые проверки

- `unit-004-command.json`: 153 tests, exit 0 (23 новых guardrail tests).
- `gate-001/OFFLINE-RESULTS.json`: 12 development worlds × 13 positive/negative
  mutations = 156 случаев, 2028 raw files. Подделки, потери, ошибки и пустые/неизвестные
  знаменатели проверяются раздельно. Fixtures используют private oracle и не являются
  свидетельством естественного формирования гипотез моделью.
- Настоящий Docker/MCP/Responses-fixture pipeline: F1 positive rate=1;
  S1 forged predecessor hash rate=0 при всех completed; C0 rate=null.
  15 свежих контейнерных контекстов, 54 scripted Responses, 351 raw files.
  Seed controlled history в natural A не передаётся; scripted provider является
  тестовым дублем, а не скрытым участником модельной серии.
- `FINAL-RAW-RECHECK.json`: 377 сохранённых случаев / 6451 raw files повторно
  прочитаны. Прежние 204 offline, 12 controller и 2 provider основных outcomes
  не изменились; новые 156 offline и 3 controller также воспроизведены.
- PyCharm error inspections: errors отсутствуют; Git diff проверен.

## Остаток исследования

Теперь нужен расчёт мощности **полного** A–E endpoint совместно с conservative
guardrail и кластеризацией по мирам. Предыдущие 27000 draft-v1 симуляций не заменяют
его. Затем T2 development protocol, pilot lock, фактическая доступность модели,
pilot/calibration, final preregistration, held-out серия и научный отчёт.
Ни успешность V1, ни преимущество S/F, ни научное завершение здесь не заявляются.
