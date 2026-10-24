# E009 — изолированный MCP handoff (инфраструктурный этап)

Дата: 2026-10-24. **Не модельный результат и не завершение E009.**

## Что реализовано

- `e009_broker.BinaryMCP`: отдельный настоящий MCP subprocess на каждом этапе;
  stdin/stdout записываются как фактические binary frames (base64 + длина), включая
  initialize, notifications и tools. Это не повторная сериализация SDK objects.
- `MemoryBroker.call/publish`: назначенные read/publish/source-verification,
  V1 warnings только для F1/S1, отсутствие произвольных hashes, shell и file tools.
  Один read/context, два publication attempts, три verifier calls.
- `publish` отдельно сохраняет public memory и private measurement; один CAS
  checkpoint указывает на оба уже сохранённых объекта. При переполнении полного
  read envelope указатель не меняется; orphan object остаётся в журнале.
- 8192 UTF-8 bytes ограничивают весь фактически передаваемый worker reply:
  compact JSON `{"result": ...}` с origin, stage, sha256, trust и LF.
  Backend MCP bytes считаются отдельно. Будущий Responses wrapper/token usage
  ещё не измерен; нельзя выдавать это число за полный размер API input.
- Публичные bytes и server-generated provenance не содержат measurement digest,
  предыдущий measurement snapshot или хэш закрытого каталога будущих свидетельств.
  E не может публиковать. C0 не получает даже хэш прежней памяти.
- `e009_sandbox_gate` использует прежнюю Docker policy без изменения E003–E008;
  новый runtime смонтирован read-only. Ни каталог source/gold, ни state DB,
  ни ключи не смонтированы в worker.

## Наблюдавшиеся проверки

Артефакты: `artifacts/e009-001/sandbox-001/` вне Git-репозитория.

1. `gate-001`: F1/S1/C0 × A–E = 15 контейнеров, все проверки инфраструктуры
   прошли. Backend MCP: 29620 bytes stdin, 249804 bytes stdout. 185 файлов
   повторно открыты по manifest. Commit реализации: `888104d`.
2. Расширение unit tests выявило два реальных дефекта: JSON exponent overflow
   (`1e999`) принимался как infinity; существующий task допускал смену condition
   F1→F0. `unit-002-command.json`: exit 1, два failed assertions.
   Исправления: finite float parser и неизменная condition в checkpoint index.
3. `unit-003-command.json`: 86 targeted tests, exit 0.
4. `gate-002`: повторный source-bound прогон после изменения кода. 15 новых
   контейнеров; C в каждой из трёх цепочек действительно убит `docker kill`
   после MCP checkpoint и до доставки publication receipt. C exit 137;
   A/B/D/E exit 0. Новый брокер D читает durable C через новый MCP subprocess.
5. Во всех трёх условиях отдельные container IDs и actor IDs. F/S передают
   только явно опубликованные события; C0 — ни одного старого события.
   Случайные canaries из measurement отсутствуют во входах наследников.
6. Чистый boundary probe: exit 0; synthetic API_KEY positive control: exit 2;
   synthetic private gold mount positive control: exit 2. Проверки используют
   фиктивные значения, а не настоящий credential/пользовательские данные.
   Root read-only, uid 65534, dropped capabilities, no-new-privileges, network none,
   запрет host paths/network и read-only runtime проверены.
7. Командоподобный текст сохранялся как literal data; marker-файл не появился.
   Произвольные get_object/hash-selected read/shell, повторный read и E publish
   отвергнуты. Это проверка scripted worker/broker, не LLM prompt-injection rate.
8. PyCharm: после исправления type annotation — без замечаний для broker/gate.
   IDE build сообщил success, но с ограничением сбора diagnostics;
   основное воспроизводимое доказательство — реальные Python/Docker проверки.

## Не закрытые риски и следующий этап

- Runtime пока deterministic fixture, без Responses loop. 0 model/API calls.
  Нет BRI, accuracy, superiority или свидетельства «внутренних убеждений» LLM.
- Этот gate покрывает F1/S1/C0, а не всю factorial/robustness серию. FULL-JOURNAL
  ещё требует отдельной разрешённой архивной проекции; T2 не реализован.
- `e009_raw` replay пока относится к прежним 204 fixtures; новый wire audit
  проверяет точные bytes/request-response matching и изоляцию, но ещё не
  является независимым end-to-end model-output BRI replay.
- Docker network-none и mount audit не доказывают отсутствие container escape.
- Научные gates остаются: модельный runtime/controller, capability binding
  к episode/track/condition, private end-to-end scoring, provider retry/STOP/usage,
  natural guardrails, power полного endpoint и false-retraction guardrail,
  T2 development protocol, pilot lock, actual model check, pilot/calibration,
  final preregistration и только затем held-out.
- Старые результаты не перезаписываются; `gate-001` и failed unit run сохранены.
  Draft остаётся `preregistered=false`. Настоящий API_KEY не записывался.

## Транзакция

Используется прежний набор ролей MODIFIED_FILE.zip / DIFF_FILE.json /
VERIFICATION.txt / ROLLBACK.sh. Новый probe сравнивает одинаковый вход:
public="only-public", private="PRIVATE-DO-NOT-FORWARD", read budget=600.

BASELINE: broker отсутствует. MODIFIED: public память читается, private marker
не передаётся, metadata overflow отклоняется. ROLLBACK: broker отсутствует;
hash restored ZIP равен pristine baseline. Полные команды, stdout/stderr,
exit statuses и hashes — в `SANDBOX-TRANSACTION.json` и общем VERIFICATION.txt.
