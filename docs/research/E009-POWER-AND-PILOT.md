# E009 — полный endpoint, мощность и первый пилот

Дата: 2026-10-24. Это промежуточный отчёт планирования, не итог E009.
Исходная спецификация, E003–E008 и результаты предыдущих gates сохранены.

## Выполненная матрица

`research/e009_power_full.py` моделирует два полных A–E повтора на мир,
F0/F1/S0/S1, общую сложность мира, коррелированные ошибки между условиями,
потери supported-слотов, технические сбои и dependent skips. Любая ранняя
ошибка остаётся в полном BRI; позднее исправление не стирает её.
Это гипотетические процессы, а не измеренные способности модели.

| Сценарий | Прирост успешности стадии V1 | Ошибка стадии | Потеря слота V0 / V1 |
|---|---:|---:|---:|
| null | 0 | 0,003 | 0,001 / 0,001 |
| safe-small | 0,035 | 0,003 | 0,001 / 0,001 |
| safe-strong | 0,07 | 0,003 | 0,001 / 0,001 |
| unsafe-v1 | 0,14 | 0,003 | 0,001 / 0,03 |
| high-failure | 0,07 | 0,03 | 0,001 / 0,001 |

Structured gain=0,01 кроме null. Параметры и распределения зафиксированы в коде
и CONFIG.json; они не подгонялись к скрытым модельным результатам.
200 экспериментов в каждой из 20 ячеек, N=60/120/240/480,
10000 paired world bootstrap ресэмплингов/эксперимент, exact sign-flip и Holm.
Все 4000 исходов сохранены, exit=0, stderr пуст, время 350,10 s.

| N | safe-small: test / full decision | safe-strong: test / full decision |
|---:|---:|---:|
| 60 | 0,270 / 0 | 0,925 / 0 |
| 120 | 0,670 / 0 | 0,995 / 0 |
| 240 | 0,955 / 0,005 | 1,000 / 0,055 |
| 480 | 1,000 / 0,360 | 1,000 / 0,610 |

При N480 safe-strong эффект 0,2067, full-decision MC95 CI [0,5409;0,6749].
Safe-small эффект 0,1033, full-decision CI [0,2967;0,4286].
Unsafe-v1 и high-failure не прошли полное решение ни разу при любом N;
при 0/200 верхняя Wilson95 MC граница 0,01885, а не ноль.
При null частота хотя бы одного Holm rejection:
N60=0,025 [0,0107;0,0572], N120=0,035 [0,0171;0,0705],
N240=0,045 [0,0239;0,0833], N480=0,020 [0,0078;0,0503].
Это совместимо с ограничением 0,05, но 200 симуляций не доказывают
универсальную корректность уровня и имеют заметную MC неопределённость.

## Необходимое исправление safety inference

Percentile bootstrap при всех нулевых потерях имеет верхнюю границу 0.
В zero-event audit вероятность не увидеть ни одного события при истинном
риске 3% и N60 равна 0,1608. Поэтому до первого модельного результата
описательная bootstrap-граница заменена в decision gate на консервативную
инверсию ограниченной Bernoulli-KL границы. Абсолютная U95<=5%;
парная U95 прироста<=2 п.п. Формулы и допущения — E009-HYPOTHESES.md.
Положительный тест BRI не достаточен, и пороги не ослабляются ради мощности.

Основание ограниченной вероятностной границы:
[Hoeffding, 1963](https://www.tandfonline.com/doi/abs/10.1080/01621459.1963.10500830).
Ограничения вырожденного bootstrap и парного ресэмплинга:
[SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).
Реализация собственная, SciPy не зависимость. Python backend — stdlib;
NumPy backend использует row indices через Generator.integers, не multinomial.
Окружение симуляции: Python3.12.14, NumPy2.3.5 из существующего bundled runtime.
PRNG Python и NumPy различаются; воспроизводимость привязана к backend/build,
а не обещает одинаковые draws между backend или версиями
([NumPy compatibility](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/compatibility.rst)).

## Feasibility, N и ресурсы

Отдельно перечислены все 576 миров; 576 feasible, 0 исключены.
Четыре семьи по 144. Oracle-supported A–D слоты: [3,5,3,5] для 288 миров
и [3,3,3,3] для остальных 288. В симуляции слоты не зависят от ответов модели.
После 96 non-test reserved остаётся максимум 480 возможных test миров.
Ни один кандидат не обеспечил 80% полного решения в рассмотренных сценариях.
N не заморожен. Следующий шаг — измерить реальные операционные параметры
pilot, а не объявлять существующий генератор достаточным по архитектуре.

Основная серия при N480: 480*8 условий*2 трека*2 повтора*5 стадий=76800 контекстов.
При предположении 60–180 s/контекст последовательное время 1280–3840 часов.
Sensitivity на весь контекст: input/output 12000/4000, 40000/12000,
120000/40000 tokens; это не измерения и не лимит пользователя.
Стоимость шлюза неизвестна, dollars=null. Pilot, T2 development, robustness,
retries, rate-limit waits и host/MCP compute сверх этих оценок.
Стоимость успеха при нуле успехов undefined, не 0. Amortization: N=1/10/100/1000.
Если pilot показывает, что confirmatory design неосуществим, это фиксируется
до heldout с новой явной предрегистрацией, без ретроспективного ослабления gate.

## Pilot lock и реальные запросы

После офлайн-проверок зафиксирован pilot-001/PLAN.json:
SHA256 `0ec03cff30061b12179239b2ac95fb19a614254ed3481e1c15f5ecfe7f4a81c8`.
12 новых миров, F0/F1/S0/S1/FULL-JOURNAL, natural/controlled, один повтор:
120 цепочек, до600 fresh contexts. Порядок условий/треков рандомизирован
внутри мира. Отдельные 12 train и12 validation миров T2, оба независимы
от pilot и12 development. Всего96 резервируются вне будущего test.
Heldout корпус ещё не создан.

T2-a и T2-b: независимые контексты разработчиков, одинаковые train/validation,
без данных другой линии, без gold/test, включение обеих линий в итог.
До10 developer contexts и24 train/validation episodes/линию, расходы отдельно.
Machine-native формат допустим; decoder/protocol фиксируются до test.
Эти T2 development runs ещё НЕ выполнены.

Выполнен прямой HTTPS Responses запрос предпочитаемой gpt-6.1-sol;
models list не использовался как фильтр. Шлюз вернул назначенную модель,
одна transport attempt, reported313 input и5 output tokens, unknown usage=0.
Это только gateway-reported identity, не независимая проверка весов.
Запущена первая назначенная цепочка: world321/F1/natural.
Результат цепочки и точные расходы читаются из immutable receipt/ledger;
данный абзац фиксирует старт, а не предполагает её успех.

Фактический первый исход: A completed; B failed/invalid_response;
C/D/E upstream_missing. Семь Responses calls, семь transport attempts,
15765 input и3053 output tokens по отчётам шлюза. Независимый replay
проверил55 raw files без изменения: technical_complete=false,
natural revision rate=null, не успешное исправление.
У A семь graph propositions используют from/to; oracle требует source/target.
Публичный контракт не задавал точные JSON-поля edge/path. Поэтому нельзя
выдать этот форматный сбой только за недостаток эпистемических возможностей модели.
Исправление контракта требует явной pilot amendment, не нормализации старых ответов.

Отдельный новый diagnostic call на том же публичном B input подтвердил,
что шлюз вернул три function_call несмотря на parallel_tool_calls=false.
Строгий одновызовный parser отклонил batch: invalid function call batch.
Сохранён raw diagnostic response, SHA и usage2583/984. Он НЕ заменяет
исходный assigned outcome. Точный первоначальный отклонённый B body не сохранён
старым adapter; доступны его SHA/model/usage/HTTP200, поэтому причина первоначального
отказа остаётся гипотезой, а не реконструированным фактом.
До следующего pilot assignment нужны прозрачная protocol amendment,
сохранение отклонённых безопасных response bodies и совместимая стратегия
tool batches с проверкой порядка/изоляции. Старый lock и первый исход остаются.
Всего на этом срезе9 реальных transport attempts: availability1+pilot7+diagnostic1;
18661 input,4042 output, unknown usage0, денежная цена неизвестна.

API_KEY передаётся getpass через неэхирующий терминал только в память
доверенного host process. Значение не входит в argv, файл, prompt, worker env
или shared state. Первоначальный stdin без PTY завершился до запроса
с `credential missing on stdin`; затем использован getpass. Это не модельный отказ.
TLS verification включён, redirects/proxy environment отключены.
Серия не переключает alias автоматически. Повтор недоступности append-only,
не ранее60s после завершённой неудачной round; внутри до4 bounded attempts.
Rate limits/Retry-After сохраняются глобальным transport ledger.
Незавершённые orphan requests/assignments не повторяются молча.

## Свидетельства и дальнейшее действие

Внешний каталог:
`C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e009-001\power-001`.
FEASIBILITY.json, ZERO-EVENT-AUDIT.json, full-001/CONFIG.json,
full-001/SUMMARY.json и20 per-cell JSON, RESOURCE-PLAN.json.
Полные команды/stdout/stderr/exit — *-command.json.
Пилот:
`C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e009-001\pilot-001`.

15 statistics tests и10 live-wrapper tests проходят. Сохранён исходный сбой
трёх mocked availability tests: mkdir зависел от побочного эффекта provider;
исправлен parents=True, затем25/25 PASS. Старые153 E009 tests учтены отдельно,
их результаты не выдаются за новый повторный запуск. IDE error inspection:
пять новых/изменённых Python файлов, проблем не сообщено.

Продолжение: независимый replay каждой фактической цепочки; измерение ceiling/floor,
сбоев, latency, памяти и guardrail; полная pilot/calibration, обе T2 линии;
final preregistration, heldout, robustness, независимый анализ и итоговый отчёт.
Не выбирать только удачные цепочки, не переписывать уже назначенные outcomes.
