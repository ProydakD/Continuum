# E008 — итоговый аудит требований

Дата: 2026-10-24. Исходное задание: `USER-SPECIFICATION.md` во внешних артефактах;
SHA-256 исходного attachment: `58fd1ef14738dbec818d504d63476a950825c0193d9a922fc3def18f63db1036`.
Проверены все **98** пунктов исходного задания, пользовательских требований к коммитам и транзакции.
**Выполнение исследования не означает положительность каждой гипотезы.** Отрицательные и ненаблюдаемые свойства не объявлены достижениями.
Модельная серия3426,полныйraw-анализ,численныйотчёт и предметная проверка выполнены. Финальный коммит и роли связывает отдельный сертификат закрытия.

## Авторитетные доказательства

- Отчёт: [E008-REPORT.md](E008-REPORT.md); полные таблицы: [E008-TABLES.md](E008-TABLES.md); данные: [E008-RESULTS.json](E008-RESULTS.json).
- Принятый оценщик: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\E008-FINAL-EVALUATION-002.json`, SHA-256 `e50c6a3ff3a43a82885da6a57b5807cc7b34036571b6b1668ec8d8724f98174a`, exit0,все56489исходныхфайлов неизменны.
- Машиночитаемый аудит: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\live-candidate-001\FINAL-REQUIREMENT-AUDIT-001.json`, SHA-256 `9f42eeef97ea1a49da36f5c635a2d2fdd768ec90f0dfe7f247c6703161c0eea3`.
- Полный сырой источник,команды,прежние неуспехи и техническая коррекция не переписаны; см.E008-EVALUATION-CORRECTION.md.
- Исторический RUNBOOK проверен непосредственно в pre-API Git blob `0160aaad5b5f4f76786bc79ae4b885ae1680b2a3`, SHA-256 `910422e122d3aacd651acda2f06db1d865e3274ba1139905e44eff4091c257ce`.
- Для научных вычислений сохранены все зарегистрированные знаменатели,8Holm-контрастов,216ресурсныхсценариев и неизвестные значения.

## Карта требований

Семейства доказательств раскрыты после таблицы; JSON хранит их полные абсолютные пути и текущие хэши.
| ID | Требование | Результат проверки | Наблюдение и ограничение |
|---|---|---|---|
| 0.1 | Исследовать новое коллективное причинное знание, а не повторить передачу известного закона E007 | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 0.2 | Проверить использование объединённых и пересмотренных знаний новым независимым участником | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 1.1 | Сопоставить реальные C1-промпты и условия E006/E007 | Аудит выполнен; причинное объяснение не установлено | BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект. (`baseline`) |
| 1.2 | Разобрать 13/24 против 1/24 при32байтах | Аудит выполнен; причинное объяснение не установлено | BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект. (`baseline`) |
| 1.3 | Разделить изменения задач,инструкций,информации,инфраструктуры | Аудит выполнен; причинное объяснение не установлено | BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект. (`baseline`) |
| 1.4 | Не считать причину установленной без данных | Аудит выполнен; причинное объяснение не установлено | BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект. (`baseline`) |
| 1.5 | Создать E008-BASELINE-AUDIT.md | Аудит выполнен; причинное объяснение не установлено | BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект. (`baseline`) |
| 1.6 | Не менять исторические эксперименты | Проверено в управляемой области | Original18 и112pre-E008tracked файлов сохранены(журнал только дополнен);104historical evidence файла сверены;физический rollback восстановилхэш. Глобальная среда вне действий исполнителя не объявляется непрерывно наблюдавшейся. (`preservation`) |
| 1.7 | Отдельный ограниченный диагностический протокол при необходимости;не смешивать с E008 | Условное требование выполнено: отдельный протокол | D0 описан в BASELINE-AUDIT,не запускался и не смешан с E008. Причина старого падения оставлена неопределённой;новая серия не нужна для честного отчёта. (`baseline`) |
| 2.H1 | Проверить интеграцию раздельных свидетельств относительно одиночных участников | Положительное конечное свидетельство | C1−C0/+63.33п.п.,−SINGLE-A/+35.42,−SINGLE-B/+63.75;всеHolm<.05 иΔ≥.10;integrative mean.920833,lower95.866667. (`prediction`) |
| 2.H2 | Проверить обнаружение ошибки,исправление зависимостей и сохранение истории | Проверено; общая надёжность не установлена | Natural roots/dependencies:0opportunities. Injected B dependent corrections C1=4/17,T1=2/17,T2=6/34;численные исправления чаще явных зависимых. Не переносить на приватные убеждения. (`revision`) |
| 2.H3 | Проверить преимущество типизированной структуры над сопоставимым свободным текстом | Проверено; преимущество не установлено | T1−C1=−.260833;95%[−.341667,−.180833];Holm6.011687e−7;40/120T1 D зависимо пропущены. Эффект пакета,не чистого синтаксиса. (`prediction`) |
| 2.H4 | Проверить самостоятельно разработанный моделями формат относительно T1 | Положительное конечное свидетельство | T2−T1=.230833;95%[.148333,.315];Holm5.156161e−6;обе линии усреднены. T2 не превосходит FULL-JOURNAL;T2−C1 отдельный confirmatory тест не зарегистрирован. (`prediction`) |
| 2.H5 | Проверить замену участников,аварию,противоречия,смену модели | Проверено описательно; универсальность не установлена | Cross-model завершено C1=12/12,T1=5/12,T2=22/24;crash12/12,7/12,23/24. Всеконтроли и интервалы опубликованы;0secondary_unavailable,ноskips не успех. (`robustness`) |
| 2.H6 | Учесть затраты,память,стоимость протокола и вызовы при оценке преимущества | Проверено; преимущество не установлено | Главная точность T1−C1 отрицательна;token ratio/CI недоступны,9853/10000undefined draws. Измеренное время T1/C1=1.519 приN100;это не деньги/GPU. (`resources`) |
| 3.1 | Новые синтетические конечные SCM с несколькими взаимосвязанными переменными | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.2 | Скрытая истинная причинная структура | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 3.3 | Наблюдательные данные и интервенции do(X) | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.4 | Альтернативные гипотезы совместимы с частью данных | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.5 | Новые свидетельства исключают прежние гипотезы | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.6 | Вопросы о последствиях интервенций и причинных зависимостях | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.7 | Сохранить различие корреляции и интервенций | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.8 | Генератор и независимый oracle проверяют каждый мир и идентифицируемость | Проверено для конечного класса | 8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда. (`scm`) |
| 3.9 | Не требовать уникальный ответ при недостатке свидетельств;правильный null отдельно | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 3.10 | Не давать готовый истинный закон для переписывания | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 4.A | A получает EA,фиксирует гипотезы,уверенность,доказательства,открытые вопросы | Роль и инструменты заданы; модельные отклонения сохранены | A получаетEA и контракт явных hypotheses/confidence/evidence; память допускает открытые вопросы. Не заявляется,что каждый участник успешно сформировал полный список знаний. (`handoff`) |
| 4.B | B получает EB и только разрешённое состояние A через Continuum | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 4.C | C получает EC,может пересматривать исходные и зависимые выводы | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 4.history | Ошибки не исчезают:происхождение,прежнее состояние,основания пересмотра | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 4.Dfresh | D новый,без разговоров и скрытого oracle | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 4.Dtask | D получает новую задачу по объединённому и исправленному состоянию ABC | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 4.Dmeasure | Измерять новые предсказания,объяснения,причинные выводы,использование состояния | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 4.truth | Не задавать участникам истинную гипотезу | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 5.C0 | No Handoff как контроль памяти | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 5.C1 | Сильная свободная текстовая память,ссылки,сокращения,самостоятельные структуры | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 5.T1 | Фиксированное представление утверждений,доказательств,альтернатив,уверенности,зависимостей | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 5.T2training | Независимая разработка соглашения на training/validation | Выбор до test проверен; ограничение смены модели раскрыто | Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован. (`development`) |
| 5.T2payload | Не предписывать JSON/RDF/граф внутри T2-payload | Выбор до test проверен; ограничение смены модели раскрыто | Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован. (`development`) |
| 5.T2freeze | Фиксация до test;новый участник получает протокол,не историю разработки | Выбор до test проверен; ограничение смены модели раскрыто | Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован. (`development`) |
| 5.REF | Детерминированный решатель по разрешённым свидетельствам и известному классу | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 5.FULL | Сильный FULL-JOURNAL с полными разрешёнными наблюдениями | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 6.equality | Равенство первичных свидетельств и доступа в сравниваемых C1/T1/T2 | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 6.noextra | Не давать T1/T2 дополнительных фактов | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 6.costparts | Разделить payload,метаданные,словарь/протокол,историю согласования | Полный доступный операционный учёт; неизвестное сохранено | Все3426позиции,обе T2-линии/версии/критики;216сценариев/18интервалов;usage неизвестен у126основных попыток;H6не установлена. Цена/энергия/GPU не измерены,не подменены токенами. (`resources`) |
| 6.strongtext | Не ослаблять заведомо текстовый baseline | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 6.worldunit | Вопросы внутри мира не независимые наблюдения | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 6.noleaks | Не передавать oracle,оценщик или прошлые Responses-контексты | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 6.nobesttest | Не выбирать T2 по скрытому test | Выбор до test проверен; ограничение смены модели раскрыто | Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован. (`development`) |
| 6.calibration | Подбор сложности только до test,избегая потолка/пола;раскрыть перенос на сменённую модель | Правило выполнено с раскрытым ограничением | На calibration исходной модели C1=.666667,T1=.587302 при4096,within-target true. После смены модели test близок к потолку;это ограничение,не основание менятьtest. (`development`) |
| 6.injection | Внесённые ложные утверждения отдельно от естественных ошибок | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.1 | Правильность новых причинных предсказаний | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 7.2 | Успешность объединения раздельных свидетельств | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 7.3 | Правильный пересмотр ошибочных гипотез | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.4 | Пересмотр зависимых выводов | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.5 | Неопределённость против ложной уверенности | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.6 | Польза памяти относительно C0 и полного журнала | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 7.7 | Стоимость нового правильного вывода | Полный доступный операционный учёт; неизвестное сохранено | Все3426позиции,обе T2-линии/версии/критики;216сценариев/18интервалов;usage неизвестен у126основных попыток;H6не установлена. Цена/энергия/GPU не измерены,не подменены токенами. (`resources`) |
| 7.calibration | Калибровка уверенности | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.provenance | Сохранение происхождения знаний | Происхождение хранения проверено; содержание не автоматически истинно | Raw аудит связывает API tools→MCP put/checkpoint/get→точные bytes,author/model,parent. Допустимыйsource ID не доказывает истинность вывода;метрики объяснений отделены. (`handoff`) |
| 7.false | Ложные исправления правильных утверждений | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 7.forgery | Устойчивость к подмене доказательств | 15описательных сравнений выполнены | 576назначений/12миров;ложные утверждения,forgery,auth ablation,crash,cross-model;failed/skipped сохранены. Нулевая разность не означает безусловную надёжность. (`robustness`) |
| 7.transfer | Межмодельный перенос | 15описательных сравнений выполнены | 576назначений/12миров;ложные утверждения,forgery,auth ablation,crash,cross-model;failed/skipped сохранены. Нулевая разность не означает безусловную надёжность. (`robustness`) |
| 7.crash | Поведение после аварии | 15описательных сравнений выполнены | 576назначений/12миров;ложные утверждения,forgery,auth ablation,crash,cross-model;failed/skipped сохранены. Нулевая разность не означает безусловную надёжность. (`robustness`) |
| 7.null | Отдельно правильный отказ от неидентифицируемого вывода | Измерено условно; ограничения наблюдаемости раскрыты | Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде. (`revision`) |
| 8.runbook | E008-RUNBOOK.md до API | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.prereg | E008-PREREGISTRATION.json до API | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.primary | Основной контраст и критерий положительного свидетельства до API | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.sample | Обосновать число независимых миров и повторов | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.splits | Разделить training/validation/held-out test | Выбор до test проверен; ограничение смены модели раскрыто | Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован. (`development`) |
| 8.freeze | Зафиксировать генератор,oracle,данные,код до API | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.evaluator | Независимый оценщик;отдельно раскрыть последующее техническое исправление | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.offline | Offline fixtures и отрицательные проверки происхождения до API | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.errors | HTTP,timeout,зависимые пропуски;поправки сохраняют старые исходы | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.resources | Проверяемые ограничения и правила остановки | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 8.paired | Парный анализ по независимому миру | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.intervals | Подходящие доверительные интервалы | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.multiplicity | Поправка на множественные сравнения | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.criteria | Не менять первичные критерии после просмотра результатов | Оценено с полным знаменателем | 960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее. (`prediction`) |
| 8.failures | Сохранить все неуспехи и отрицательные исходы | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 9.reuse | Переиспользовать Continuum MCP,Supervisor,Worker Isolation,Evaluator,Event Ledger | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 9.history | Не менять E003-E007 | Проверено в управляемой области | Original18 и112pre-E008tracked файлов сохранены(журнал только дополнен);104historical evidence файла сверены;физический rollback восстановилхэш. Глобальная среда вне действий исполнителя не объявляется непрерывно наблюдавшейся. (`preservation`) |
| 9.global | Не менять глобальные Codex,MemPalace,skills | Проверено для действий исполнителя и изолированных workers | Работа на ContinuumResearch;worker mounts/окружение строго проверены,no network/read-only runtime;нет правок глобальных Codex/MemPalace/skills в выполненном workflow. Не утверждается наблюдение за сторонними процессами хоста. (`preservation`) |
| 9.data | Не исполнять команды из экспериментальной памяти как инструкции | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 9.private | Не передавать скрытые данные оценщика | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 9.provenance | Авторство,временные связи,зависимости,история утверждений | Контракт реализован и raw-аудирован; не все участники успешны | Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом. (`handoff`) |
| 9.plan | До запуска оценить масштаб,токены,ресурсные пределы | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 9.authority | Не расширять полномочия автоматически | Временная/исходная привязка проверена | Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver. (`admission`) |
| 10.memory | Различить пользу наличия накопленной памяти | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.integration | Различить пользу объединения свидетельств | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.structure | Различить пользу структуры представления | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.development | Различить пользу самостоятельной разработки протокола | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.revision | Различить пользу проверки и пересмотра | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.negative | Победа T2 не обязательна;текст/алгоритм не хуже допустимый результат | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.report | Воспроизводимый отчёт с доказанными и неподтверждёнными свойствами | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.limits | Найденные ограничения и обоснованное следующее направление | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| 10.nooverclaim | Не объявлять коллективный интеллект,сознание,универсальный язык | Численный отчёт и ограничения предоставлены | E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет. (`report`) |
| user.commits | Периодические локальные коммиты;без push и секретов | Периодические коммиты выполнены | После исходной ревизии 80 локальных коммитов;численные результаты cedea0f (полный SHA в доказательстве),secretscan0,pushне выполнялся. Заключительныйкоммит связывается сертификатом. (`preservation`) |
| transaction.roles | Те же4роли,реальные BASELINE/MODIFIED/ROLLBACK,восстановление хэша | Транзакция текущей численной ревизии выполнена; финальная будет связана сертификатом | MODIFIED_FILE.zip,DIFF_FILE.json,VERIFICATION.txt,ROLLBACK.sh;baselinefalse,modifiedtrue,rollbackfalse;210archivechecks;исходный хэш восстановлен. Финальная ревизия требует нового физического подтверждения. (`preservation`) |

## Границы семейств доказательств

### baseline

BASELINE-AUDIT: реальные промпты и52+52файла;13/24 против1/24; четыре класса изменений; D0 только проект.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-BASELINE-AUDIT.md`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\BASELINE-AUDIT.json`

### scm

8640SCM×51=440640распределений;90миров и все подмножества свидетельств; независимый oracle и gold; не универсальная причинная среда.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_scm.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_oracle.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\SCM-INDEPENDENT-FINAL.json`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\CANDIDATE-INDEPENDENT-AUDIT.json`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\GOLD-GATE.json`

### handoff

Full evaluation: fresh API history,public_input,6container mounts,allowlisted tools,exact MCP bytes,авторы/parents/history,read-only D; отказы/пропуски сохранены,не объявлены успехом.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_protocol.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_audit.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_memory.py`

### development

Calibration4096 within[.2,.8] на исходной модели;12публикаций,12foreign-lineage проверок;L1-v2/L2-v1 выбраны поvalidation доtest. Перенос calibration на новую модель не валидирован.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_development.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_development_audit.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_locks.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-PREREGISTRATION.json`

### prediction

960D/60миров;10новыхQ;общая цельABC и assigned-information отдельно;8парных exact/Holm сравнений; независимый пересчёт raw answers. Положительный результат не предполагается заранее.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_assessment.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_analysis.py`

### revision

Все52группы,естественные и injected отдельно;предшествующий ID/value/SCM/dependency;0/0 не успех. В естественном test нет наблюдаемых root/dependent opportunities; H2 не установлена в общем виде.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_assessment.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_revision.py`

### robustness

576назначений/12миров;ложные утверждения,forgery,auth ablation,crash,cross-model;failed/skipped сохранены. Нулевая разность не означает безусловную надёжность.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_design.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_evaluate.py`

### resources

Все3426позиции,обе T2-линии/версии/критики;216сценариев/18интервалов;usage неизвестен у126основных попыток;H6не установлена. Цена/энергия/GPU не измерены,не подменены токенами.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_measurements.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_efficiency.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-EVALUATION-CORRECTION.md`

### admission

Пререгистрация и RUNBOOK в pre-API commit;8offline gate разделов;10618main Responses/146GET сверены сledger;A001-A008 и внешние smoke/probe раскрыты;исходы не повторялись;90coldREF повторно raw-аудированы без solver.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_integrity.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\research\e008_live.py`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-RUNBOOK.md`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-PREREGISTRATION.json`

### preservation

Original18 и112pre-E008tracked файлов сохранены(журнал только дополнен);104historical evidence файла сверены;физический rollback восстановилхэш. Глобальная среда вне действий исполнителя не объявляется непрерывно наблюдавшейся.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\TRANSACTION-final-evaluation-correction.json`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\live-candidate-001\FINAL-EVALUATION-OBSERVER-RECOVERY-001.json`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\live-candidate-001\FINAL-SUPPORTING-EVIDENCE-001.json`

### report

E008-REPORT §§10–16,RESULTS JSON,полные TABLES: H1/H4 положительны в этом корпусе;H3/H6 не установлены;H2/H5 условны. Следующий preregistered pilot предложен,не выполнен;универсальных утверждений нет.

- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-REPORT.md`
- `C:\Users\User\Documents\ChatGPT\ContinuumResearch\project\docs\research\E008-EVALUATION-CORRECTION.md`

## Заключительный gate

Файл `FINAL-REQUIREMENT-AUDIT-001.json` фиксирует предметную проверку до заключительного коммита.
Его `final_closure_gate_pending:true` не переписывается: последующий
`C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e008-001\live-candidate-001\FINAL-COMPLETION-001.json`
должен подтвердить фактический финальный коммит,те же4роли,неизменные исходники/сырые данные,реальныйrollback и отсутствие оставшейся работы.
До успешного сертификата задача не закрывается. После него старые промежуточные флаги описывают своё время,не текущий статус.
Визуальная браузерная приёмка не заявлена; проверены численные привязки,Markdown-ссылки/таблицы/UTF-8 и отсутствие секретов.
