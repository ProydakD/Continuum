# E-002: исправление измерителя и Responses pilot

19 октября 2026. Это протокол малого пилота, не доказательство H-003/H-004.

## Контракт и измеритель

`research.evaluator.final_result` принимает compact/spaced JSON и JSON внутри
последнего `item.completed/agent_message`. Ровно `needs_context` поддерживается
как plain-text отказ. Произвольная проза, цитата в tool output и старый финальный
ответ перед новым некорректным ответом не засчитываются. Успешный сумматор выдаёт
`{"status":"completed_stage","stage":"A|B|C","total":INTEGER}`.
Checkpoint содержит ровно stage, total, object_sha256, claim_id.
Объект — JSON с единственным полем values (непустой массив int, не bool).

Закрытый SHA-256 канонического входа отличает массивы с одинаковой суммой.
Оценщик пересчитывает values, проверяет каждую стадию, task/object/claim/event
и связывает реальные успешные MCP-ответы с connection + request id и порядком.
`audit_raw.py` использует read-only SQLite и собственный разбор, без Store/evaluate.
Это независимая реализация в рамках одного инженерного автора, не независимый
человеческий аудит. Удаление обязательного ответа должно менять PASS на FAIL.

## Внешний режим

Старый `research.cli` сохраняет offline Ollama/fixture и запрет внешних расходов.
Отдельный `research.e002` включает Responses только явно. Выбран прямой broker:
не нужен новый образ с Codex/Ollama; один и тот же worker используется C1/T1.
Контейнер остаётся network=none, без ключа, DB, HOME хоста и oracle. Рабочие
инструменты — только read_memory/save_memory; broker переводит их в настоящий
MCP и сохраняет raw transcript. Нет shell/eval/загрузки URL из модельного текста.
Сохранённые исходные наблюдения одинаковы в обоих условиях; формат и производные
гипотезы — treatment как пакет, не отдельный эффект JSON.

Ключ читается доверенным broker из API_KEY, не из конфигурации worker.
HTTPS с проверкой имени и доверенной цепочки; без redirects, retries, downgrade.
`store=false` не гарантирует отсутствие хранения у шлюза. Модель обозначается
как заявленная шлюзом; metadata не аттестует backend.

Пользователь в текущей сессии явно разрешил API_KEY, передачу синтетики и работу
без лимитов запросов/расходов. Поэтому регистрация использует unbounded-spend,
а не выдуманный BUDGET_USD. Конечный объём исследования остаётся 6 сессий + smoke,
concurrency=1, 90/300/660 секунд, 2048 output tokens на запрос, retries=0.
Для иных finite-budget запусков SpendLedger требует подтверждённую верхнюю
цену запроса и резервирует её до отправки; ошибки тоже расходуют reservation.
Лимит или тариф OpenAI не переносится на стороннего провайдера.

## Семейство и оценка

f(x)=a*x+b+c*(x%2), конечные a/b/c. A видит чётные x: остаются три альтернативы.
B видит нечётный пример: остаётся ровно одно правило. C получает новые x, не
ответы. Seed и порядок фиксируются до ответов. Проверка генератора выполняется
программно, ответы evaluator не монтируются в worker. Мир не взят из демонстрации.

Первичная метрика: точное пересмотренное правило и все зависимые предсказания C.
Она одинакова для C1 и T1. Сохранение отвергнутых альтернатив, lineage, формат,
токены и задержки — вторичные метрики. C1 не запрещено сохранять альтернативы.
Новый E-002 journal event предшествует первому ответу модели. Старый E-002/1 и
отрицательные E-001 результаты не переписываются.

## Порядок запуска

Сначала unittest, integration_mcp, validate_journal, затем НОВЫЕ legacy
prepare/preflight/run/evaluate для handoff/empty/injection и independent checker.
Gate содержит хэши кода и команды. После него:

```text
python -m research.e002 prepare --study-id NEW_ID --gate ABSOLUTE_GATE_JSON
python -m research.e002 metadata --study ABSOLUTE_STUDY --authorize-responses --unbounded-spend
python -m research.e002 smoke --study ABSOLUTE_STUDY --authorize-responses --unbounded-spend
python -m research.e002 run --study ABSOLUTE_STUDY --condition CONDITION --stage STAGE --authorize-responses --unbounded-spend
python -m research.e002_evaluate --study ABSOLUTE_STUDY
```

CONDITION/STAGE — только зарегистрированный порядок. По одному запуску,
без retries. При изменении кода — новая регистрация/идентичность, не старый PASS.
Следующая подтверждающая серия требует новой выборки и нового согласования.

Контракт Responses сверялся с первичным источником:
https://developers.openai.com/api/docs/guides/function-calling
Полная stateless история внутри worker; между A/B/C нет previous_response_id.

## Артефакты и секреты

Четыре существующие роли расширяются; предыдущие версии сохраняются.
Откат действует только на переданную архивную копию и не удаляет DB, journal или
эксперименты. NEXT-SESSION-PROMPT.md уже содержал credential в исходном тексте:
его содержимое не включается в новые архивы; только хэш входного документа.
Ключ из него нельзя печатать, копировать в отчёт или передавать worker.
