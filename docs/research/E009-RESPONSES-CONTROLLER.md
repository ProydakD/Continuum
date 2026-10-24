# E009 — контроллер Responses и независимый raw replay

Дата: 2026-10-24. Commit реализации: `74da5c3`.
**Промежуточный инфраструктурный результат, не результат LLM и не финальный отчёт.**

## Реализация

`e009_execute.execute_stage/run_chain` запускает каждый A–E в новом network-none
контейнере, с новым actor и MCP subprocess. Контроллер сравнивает каждый запрос
worker с собственной реконструкцией истории и исполняет только function call,
который действительно присутствовал в ответе provider. Необъявленные инструменты
не получают дополнительных прав.

Новый `e009_runtime/responses.py` работает с обычной последовательностью Responses
items. Все output items, включая reasoning и message phase, сохраняются только
внутри текущего контекста; между A–E не передаются history, response_id или
conversation_id. Это соответствует
[официальному руководству по состоянию диалога](https://developers.openai.com/api/docs/guides/conversation-state)
и [function calling](https://developers.openai.com/api/docs/guides/function-calling).
Используется `store=false`; совместимость конкретного стороннего шлюза ещё
не подтверждена реальным запросом.

Назначение MCP task теперь связывает episode, track, condition и private evidence
digest; эти private digests не попадают в модельный input. Начальная история
поступает через ограниченное read_memory, а не дублируется в prompt.
FULL-JOURNAL читает только опубликованный архив плюс разрешённые первичные
свидетельства. Архив не строится из private measurement. Его фактический размер
считается отдельно; предел транспортного frame не выдаётся за равный F/S budget.

Добавлен одинаковый для всех условий `hash_claims`: SHA256 только предоставленных
участником JSON objects, без доступа к старому private state. Это устраняет
необоснованное требование вычислять криптографический хэш самим языковым моделям.
Стоимость вызовов будет учитываться; tool не проверяет истинность. Он ограничен
тремя пакетами до 128 объектов. F/S budget по-прежнему 8192 bytes полного read reply.

`e009_replay.replay` заново проверяет:
- внешний manifest, полный inventory и неизменность каждого файла;
- public projection, свежий prompt и provider request/body;
- всю последовательность output items, tools, function_call_output и финального текста;
- фактические binary worker/MCP frames и их длины;
- successful MCP checkpoint, objects, hashes, actor и parent binding;
- равенство публикации и private measurement фактически выданным provider arguments;
- независимый full-chain score, а не итоговую оценку/ответ из terminal.json.

## Фактические результаты

`artifacts/e009-001/controller-001/`:

- 96 targeted unit tests: exit 0.
- Smoke: S1 A–E, 5 контейнеров, 18 mock Responses calls, 117 raw files.
- Основная матрица: **12 cases, 60 назначенных контекстов, 52 реально запущенных
  контейнера, 185 mock Responses calls, 1249 raw files**.
- Положительные F0/F1/S0/S1/FULL-JOURNAL: BRI=1 у scripted reference.
  C0: BRI=null, а не успех пересмотра.
- Недопустимый get_object и переполнение read envelope отклонены; последующая
  допустимая публикация проходит. Исправления не вносятся за участника.
- Неверное состояние в B, даже с дальнейшим правильным финалом: BRI=0.
- Реальный kill C после durable commit: C exit 137, D/E completed, operational BRI=0.
  Восстановление не превращает технически незавершённую цепочку в основной успех.
- STOP перед B: A completed, остальные четыре stopped, BRI=0.
- Provider failure / incomplete response в C: failed; D/E upstream_missing,
  BRI=0, назначения сохранены в знаменателе.
- Переписанный terminal answer с заново вычисленным negative-test manifest
  отвергнут по противоречащим ему provider bytes.
- Backend MCP stdin=384085, stdout=1767850 bytes; serialized provider request bodies
  =1891689 bytes; memory replies=145025 bytes. Максимальный FULL-JOURNAL read
  =14389 bytes. Это не HTTP/TLS wire и не реальные API tokens/стоимость.

## Найденная ошибка и отрицательное свидетельство

В отдельной копии smoke artifacts изменён public census total `8` → `8.0`,
остальные трассы оставлены прежними, manifest намеренно перепривязан для проверки
самого replay. Python equality ошибочно приняла такую подмену:
`numeric-regression-001.json`, unexpected_acceptance=true, BRI=1, exit 1.

Сравнения публичных входов, requests, ответов и публикаций заменены на сравнение
типочувствительных canonical frames. Тот же сохранённый отрицательный вход теперь
отвергается: `numeric-regression-002.json`, «stage public projection changed».
Первоначальный результат не удалён и не переименован в PASS.

PyCharm errors-only inspection: без ошибок. IDE build: success с явным ограничением
сбора build diagnostics. Основная проверка — реальные Python/Docker команды.

## Ограничения и следующий шаг

Mock provider содержит заранее построенный oracle reference и намеренные ошибки.
**Ни один его BRI не свидетельствует о способности LLM, ни один mock call не
является реальным API call.** Выполнено 0 model/API requests.

Следующий исполняемый gate — E009-only HTTPS provider: неизменяемый учёт попыток,
несколько разнесённых retries, Retry-After, STOP, TLS/no redirects, unknown usage,
redaction и проверка сообщённой модели. Исторический ResponsesProvider не менять.

Затем: natural selectivity/provenance guardrails, power полного endpoint и
false-retraction guardrail, T2 development protocol, pilot lock, реальная
проверка доступности модели, pilot/calibration, final preregistration, held-out,
анализ и итоговый отчёт. Все эти пункты остаются частью исходной цели.

## Четыре роли

Сохранены прежние абсолютные role paths в общем artifacts. BASELINE и ROLLBACK:
нового контроллера нет; MODIFIED: свежий контекст, public memory=null в prompt,
отсутствие server-side conversation references, сохранение reasoning items.
Оригинальный source, 212 historical files и прежние raw outcomes не изменены.
Откат восстанавливает pristine hash; patch повторно применён. Literal commands,
stdout/stderr и exit statuses — в VERIFICATION.txt и CONTROLLER-TRANSACTION.json.
