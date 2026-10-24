# E009 — HTTPS transport и независимый учёт попыток

Дата: 2026-10-24. Промежуточный инженерный результат, **не модельный эксперимент**.
Артефакты: `C:/Users/User/Documents/ChatGPT/ContinuumResearch/artifacts/e009-001/provider-001/`.

## Изменение и границы

`research/e009_provider.py` реализует `HTTPSProvider.respond(context_id, request, timeout=...)`.
Внешние вызовы запрещены без явного `authorize=True`; реальный credential доступен только
доверенному host-процессу через `API_KEY`. Ни ключ, ни его значение не передаются sandbox,
Continuum, argv или файлам. Проверяются фиксированный HTTPS endpoint, certificate/hostname,
точный model identity, отсутствие server-side conversation IDs, максимальный размер тела.
Proxy environment и перенаправления отключены. Список моделей не является availability gate:
после научных gates понадобится прямой Responses-запрос, включая случай отсутствия модели в списке.

SQLite ledger сохраняет pending/terminal, request/response hashes, ordinal, HTTP status,
наблюдённые bytes тела, reported usage и unknown outcomes. CAS запрещает переписывать
завершение; orphan/pending и повторная идентичная logical request не исчезают при перезапуске.
Pending попытка консервативно считается submitted-or-uncertain. Usage неизвестен — не ноль;
цена неизвестна — `cost_usd=null`. Wire headers/TLS overhead не измерены.

Политика: максимум четыре попытки; backoff 2/4/8 секунд + jitter до 0.25;
Retry-After — нижняя граница, в том числе между logical requests после отказа ждать дольше
deadline. Retryable: connection failures, 408/429 и выбранные 5xx. Quota/billing,
authentication, TLS, redirects, model mismatch, malformed/incomplete response не маскируются
сменой модели или бесконечными повторами. Каждый повтор учитывается; вложенных retries нет.
Ориентиры: [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits)
и [error codes](https://developers.openai.com/api/docs/guides/error-codes).

`e009_replay.audit_transport` независимо пересчитывает totals из записанных попыток,
проверяет порядок/identity, request binding и hash/model успешного response.
Это проверка внутренней согласованности сохранённого сырья, **не криптографическое доказательство
честности провайдера или защищённость от переписывания всего внешнего evidence store**.

## Фактические проверки

- `unit-005-command.json`: 130 E009 tests, exit 0, включая 34 provider/replay tests.
- `gate-001`: настоящий Docker/MCP controller с синтетическим HTTP peer. Retry case:
  5 completed stages, 18 Responses calls, 20 HTTP attempts, BRI=1, 122 raw files.
  STOP case: 5 stopped assignments, 1 response attempt, BRI=0, 49 raw files.
  Scripted reference использует oracle и **не является LLM**.
- `TRANSPORT-REPLAY-RECHECK.json`: оба сохранённых набора повторно разобраны более строгим
  evaluator без перезаписи raw outcomes.
- `tls-008`: реальный localhost TCP/TLS/HTTP, disposable synthetic certificate/credential,
  6 cases, 8 attempts, 7 полученных POST. Untrusted certificate: 0 POST, один отказ без retry.
  503 HTML → 429 → 200: три POST с реальными паузами, 6.457 s суммарно.
  Redirect: один POST, destination не запрашивался.
  STOP до headers и внутри body: `operator_stop`, 57 ms и 21 ms после STOP соответственно.
  Deadline внутри body: остановка за 0.470 s; ровно один полученный byte учтён, response incomplete.
  Сервер закрыт; fixture API credential не найден в артефактах.
- PyCharm inspections для четырёх изменённых Python files: errors отсутствуют.

Внешний gateway не проверялся, реальных модельных вызовов **0**. Локальный TLS-сертификат
ничего не доказывает о сертификате/доступности пользовательского сервера.

## Отрицательные результаты сохранены

1. `unit-001-command.json`: первоначальные ошибки HTML 502 retry, сохранения model mismatch,
   context credential validation и endpoint control characters. Исправлены, прежний stderr сохранён.
2. `accounting-regression-001.json`: подмена terminal usage на 123456 первоначально принималась.
   После пересчёта из attempt rows тот же сохранённый negative fixture отвергнут;
   `accounting-regression-002.json`, exit 0.
3. `tls-001` проверял только outcome STOP и пропускал задержку 5 s.
   Усиленный latency gate `tls-002`/`003` провалился. Stack trace показывает main thread
   в SSL read; watcher уже завершился. `tls-004`/`005`: прямой OS socket shutdown также
   не прервал pending Windows SSL read; попытка исправления отвергнута, evidence сохранён.
4. Транспорт переведён на cancellable async stream с обязательным join cleanup до retry.
   Используется **уже установленный** `httpx2==2.14.0`, direct pin в `research/e009-requirements.txt`;
   ничего не устанавливалось, исторический pyproject не менялся. API сверено с installed source;
   [upstream async streaming contract](https://github.com/encode/httpx/blob/master/docs/async.md)
   не подменяет проверку установленного fork.
   `tls-006` выявил классификацию wrapped TLS error как network failure. Traversal exception
   cause/context исправлен; `tls-007`, финальный `tls-008` и regression tests прошли.

## Что ещё не завершено

Не проведены natural provenance/version/selectivity guardrails, перерасчёт power для
полного endpoint и false-retraction guardrail, final N, T2 development protocol, pilot lock,
прямой availability request, pilot/calibration, final preregistration, held-out серия и отчёт.
При live launch нужно явно задать request/stage deadlines, совместимые с четырьмя попытками;
fixture defaults контроллера 45/120 s не являются зарегистрированными production limits.
Модельные успехи, полнота H1–H6 и финансовая стоимость не заявляются.
