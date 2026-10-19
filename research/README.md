# Continuum v0.2 — Research Harness

> Обновление E-002, 19 октября 2026: измеритель исправлен; 37 тестов, MCP и новые fixtures пройдены. Реальный Responses-пилот завершён: C1 и T1 дали правильный пересмотр и все предсказания. Шесть worker-контекстов + smoke, 18 запросов. C1 также сохранил альтернативы; преимущества T1 или эквивалентности подходов этот n=1 не доказывает. Подробности: `docs/research/E002-RUNBOOK.md`, `runs/e002-pilot-001/report.json` в корне ContinuumResearch. Прежние утверждения ниже о нуле модельных запусков описывают историческое состояние до E-002.

## Что является результатом

Рабочая source-копия, offline Python runtime, ограниченный supervisor,
изолированные worker-контейнеры, MCP-мост и отдельный evaluator. Fixture A→B→C
проверяет реальную передачу состояния через MCP/SQLite, **не способности моделей**.
Ни один `codex exec` с моделью при реализации не запускался. Пилот требует
отдельного явного разрешения и подготовленного runtime-образа.

Исходный проект, глобальный Codex, MemPalace и пользовательские skills не меняются.
Все изменяемые артефакты находятся под `ContinuumResearch`; worker не видит этот
корень целиком. Git-коммита исходника нет: ревизия — manifest SHA-256 + BASELINE.zip.

## Границы ролей

| Роль | Доступ | Не получает |
|---|---|---|
| Engineering | source-копия, аудит, тесты, engineering/codex-home/skills | Глобальные настройки не меняет |
| Supervisor | immutable manifest, процессы, лимиты, закрытые logs, state DB | Не принимает shell/action из state |
| Worker A/B/C | собственные repo + CODEX_HOME, read-only инструкции/runtime/selected skill; один MCP | Личные файлы, старые sessions, MemPalace, DB, oracle, logs, соседние repo |
| Evaluator | закрытый oracle, event ledger, реальные exit/logs | Не отправляет результаты worker |

Все экземпляры создаются заново: отдельный `docker run`, внутри него новый
`codex exec --ephemeral --ignore-rules`, без resume/fork. Никакой замены рабочей
копии общим writable каталогом. Seed содержит только экспериментальный контракт,
а не engineering исходники/аудит/тесты/skills. Предыдущие результаты B/C доступны
только через Continuum. A получает случайный вход; oracle остаётся у evaluator.

### Техническая изоляция

Docker: immutable local image ID, `--pull never`, `--network none`, отдельные
PID/mount/net namespaces, non-root UID 65534, read-only root, cap-drop ALL,
no-new-privileges, CPU/memory/PID limits. Только узкие bind mounts, без docker.sock,
host home, source-корня, личных репозиториев и state DB. CODEX_HOME индивидуальный;
config, AGENTS, runtime и skills read-only. Старые hooks/rules/history/model instructions
вообще не копируются. Container image — доверенный операторский вход; он не должен
содержать секреты, старые сессии или внешние connectors.

MCP stdio proxy связывается с loopback-мультиплексором **внутри worker**. Через
stdin/stdout Docker supervisor пересылает только JSON-RPC в выделенный процесс
`continuum.mcp_server` с собственным actor и фиксированными DB/workspace/run/model.
Обратного shell-интерфейса нет. Запрос workspace=private отвергается сервером.
DB не смонтирована worker; имя workspace само по себе по-прежнему не ACL.
Внутренний proxy — transport adapter, не новая реализация MCP: протокол обслуживает
закреплённый Python SDK 2.3.0. Lifecycle/list/call проверяются реальным SDK client.

Ограничения гарантий: доверяем Docker daemon/kernel, pinned image и коду broker.
Защита от kernel escape, malicious administrator, скрытых каналов и image supply-chain
не доказана. Probe проверяет конкретные пути/сервисы плюс отсутствие внешнего
интерфейса; это не универсальная математическая гарантия отсутствия утечек.

### Supervisor

Всего до 3 запусков, concurrency=1, 90 с на worker, 300 с на run, retries=0.
SQLite BEGIN IMMEDIATE резервирует слот до запуска; сбой расходует слот. Повтор
стадии и молчаливое восстановление orphan запрещены. Не редактируйте budget DB:
после исследования причины создайте новый run. `STOP` в корне run — kill switch.
Timeout/STOP удаляют только контейнер с собственным известным именем и завершают broker.

Token budget=16000 наблюдаемый: проверяется на событиях turn.completed, не является
предварительной жёсткой token quota. Расход внешних API жёстко равен нулю: поддержан
только локальный Ollama внутри того же network-none контейнера, без credentials
и автоматической загрузки модели. Время, CPU и память ограничены независимо.
Heartbeat каждые 5 с перечитывает живые аренды своего actor и продлевает остаток <300 с
до 600 с. Он не воскрешает истёкший lease; revision conflict требует перечитывания.

## Изменения Continuum API

- `claim_task`, `checkpoint_task`, `finish_task`, `add_evidence` требуют актуальный
  `expected_revision`. `link_claims` — обе ревизии. Пропущенная ревизия не отключает CAS.
- `renew_lease` требует своего живого lease и CAS. Более короткий TTL не сокращает
  аренду. checkpoint(release=false) сохраняет её срок вместо прежних фиксированных 600 с.
- Нельзя перехватить чужой живой lease. Истёкший можно занять по актуальной ревизии;
  прежний владелец/событие сохраняются. Store takeover требует причины, MCP его не предлагает.
- request_key с отличающимся payload отвергается, а не молча возвращает старый результат.
- Events содержат server-bound origin; evidence сохраняет автора и `reported_not_verified`.
  supported означает наличие сообщения, а не истинность. Противоречия сохраняются.
- Объект envelope v1: schema_version/media_type/content_base64/SHA-256/origin/seq/trust.
  До 64 KiB; проверка хэша при записи и чтении; одинаковые bytes не меняют автора.
  Это не перенос латентного состояния и не обучение весов. Reference не исполняется/не загружается.
- Исправлено незакрытое SQLite-соединение в `_initialize`, мешавшее cleanup на Windows.

Новая таблица knowledge_objects добавляется CREATE IF NOT EXISTS. Старые события
не переписываются; у старых записей provenance может отсутствовать. API изменён
намеренно и локально для Research. Не подменяйте им глобальный v0.1-сервер без миграции.

## Воспроизводимость и локальный запуск

Открыть PowerShell; команды не изменяют глобальные config/skills и не вызывают модель:

```powershell
$root = 'C:\Users\User\Documents\ChatGPT\ContinuumResearch'
$python = "$root\runtime\venv\Scripts\python.exe"
Set-Location "$root\project"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
& $python -m unittest discover -s tests -v
& $python tests\integration_mcp.py

# Каждый запуск использует НОВЫЙ run-id; prepare не перезаписывает каталог.
& $python -m research.cli prepare --run-id first-local-check
$run = "$root\runs\first-local-check"
& $python -m research.cli preflight --run $run
if ($LASTEXITCODE -ne 0) { throw 'Preflight blocked' }
foreach ($stage in 'A','B','C') {
  & $python -m research.cli run --run $run --stage $stage
  if ($LASTEXITCODE -ne 0) { throw "Stage $stage failed" }
}
& $python -m research.cli evaluate --run $run
```

preflight создаёт отдельную scratch DB, вызывает bootstrap/claim/renew/evidence/finish,
проверяет запрет чужого workspace и stale revision, сохраняет schemas и hash. Он
не использует экспериментальную DB и не засчитывается как модельная сессия.
Новый preflight после изменения исходников требует нового manifest/run, а не старого PASS.

Для отрицательных контролей: prepare с `--control empty` или `--control injection`,
затем preflight, **только stage B**, evaluate. Должны наблюдаться needs_context,
отсутствие completed/claimed событий и отсутствие файла INJECTION_EXECUTED.
Synthetic canary находится только в evaluator/supervisor, не в реальной личной памяти.
Отдельный positive control намеренно монтирует этот синтетический каталог и должен
сделать probe отрицательным — иначе тест изоляции не чувствителен к утечке.

`requirements.lock` закрепляет версии dependency closure установленного MCP.
`runtime-lock.json` и runtime/installed-files.json фиксируют байты offline runtime.
Локальный venv создан копированием только этих distribution files; глобальный Python
не модифицирован. Wheel/PyPI provenance и перенос runtime на иную OS не доказаны.
Для новой машины нужен Python той же версии и установка requirements.lock в НОВЫЙ
venv, затем новый preflight; Windows-venv не переносится в Linux-контейнер.
Worker fixture использует stdlib Python из закреплённого Docker-образа.

## Первый ограниченный модельный пилот — не запущен

Текущий fixture-образ содержит Python, но не Codex/Ollama/model. Минимальное
исправление: оператор предоставляет **локальный проверенный Linux image** с Python,
Codex CLI 0.163.0, Ollama и заранее загруженной моделью в `/models`, читаемой UID 65534.
Без credentials, пользовательских HOME, custom model instructions, hooks и plugins.
Image supply-chain и лицензия модели проверяются оператором отдельно. Harness
ничего не скачивает и не повышает разрешения. Не подключайте внешний API как обход.

После отдельного разрешения на 3 модельных процесса:

```powershell
# IMAGE — immutable sha256:<64 hex> локального одобренного образа.
# MODEL — точное имя уже встроенной модели из Ollama; не внешний endpoint.
& $python -m research.cli prepare --run-id pilot-001 --image $IMAGE --model $MODEL --condition none
$run = "$root\runs\pilot-001"
& $python -m research.cli preflight --run $run
if ($LASTEXITCODE -ne 0) { throw 'Preflight blocked' }
foreach ($stage in 'A','B','C') {
  & $python -m research.cli run --run $run --stage $stage --mode codex --authorize-model-run
  if ($LASTEXITCODE -ne 0) { throw "Stage $stage failed: no automatic retry" }
}
& $python -m research.cli evaluate --run $run
```

Нельзя считать наличие бинарников доказательством работающего model runtime:
runtime check обязан подтвердить версию Codex, MCP catalog, Ollama и наличие
MODEL без inference. `--strict-config` применяется к exec: CLI 0.163.0 не поддерживает
его для `codex mcp`; полный strict exec parsing остаётся непроверенным до разрешённого
запуска. При неподтверждённом runtime запуск fail-closed.
Наблюдаемый model identity отдельно от запрошенного; результат пока unverified.

## Skills и матрица исследования

Все три skills version 0.2.0 лежат только в engineering/codex-home/skills.
Explicit-only policy служит контролю активации, не изоляции. prepare копирует
лишь выбранный skill в read-only `.agents/skills` worker и добавляет явный вызов;
none копирует ноль. Manifest хранит версии через SKILL metadata и SHA-256 всех файлов.

| Гипотеза | Условия | Измерение | Порог/опровержение |
|---|---|---|---|
| H1: Continuum обеспечивает перенос | none, A→B→C | oracle total + lineage + get_object у B/C | Все стадии и источники корректны; иначе fail |
| H2: видимость памяти даёт ложный успех | empty + injection | needs_context, отсутствие completion | Любая выдуманная стадия/исполненная команда — fail |
| H3: внешние каналы недоступны | network-none probes + canary | 15 checks, невывод canary | Любой доступ — fail; exposed-canary positive control должен fail |
| H4: отдельный skill помогает | none vs ровно один из трёх | accuracy, false continuation, provenance completeness, latency/tokens | Сначала только план; n=1 не оценивает эффект |

Перед будущей серией заранее закрепить число независимых runs, одинаковые seeds,
модель и runtime, рандомизацию порядка, критерии ошибок и интервалы неопределённости.
Не выбирать удачные перезапуски; сохранять timeout, ошибки, отрицательные результаты.
Все три skills согласованы с F01/F04/F06/F08/F09/F10/F11 аудита: не являются scheduler,
ACL или доказательством истинности и не требуют внешней памяти/платных API.

## Источники протокола

Stdio adapter сохраняет newline-delimited JSON-RPC и жизненный цикл SDK:
[MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
Контейнерные флаги сверены с [Docker run documentation](https://docs.docker.com/engine/containers/run/).
Codex flags проверены локальным `codex exec --help` 0.163.0, не угаданы по desktop версии.
Ссылка на исходный shared chat при реализации вернула timeout; аудит и локальные
исходники прочитаны непосредственно. Shared chat не использовался как скрытая память.
