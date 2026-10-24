# E009 — поправка пилота 001: схема и последовательные tool batches

2026-10-24, до heldout. Основание — первый реальный pilot-001 и отдельный
diagnostic response, а не предположение о способностях модели.

## Что меняется

- Публичная инструкция задаёт точные JSON-поля всех пяти query kinds.
  Для edge/path это source/target, не from/to. Oracle не принимает новые aliases;
  старые measurement не исправляются задним числом.
- Protocol v2 допускает до16 tool calls в одном Responses output и исполняет
  их строго последовательно, в исходном порядке. Запрос по-прежнему содержит
  parallel_tool_calls=false; толерантность к наблюдаемому поведению шлюза явная.
  Весь batch проверяется до передачи worker. Duplicate IDs, malformed arguments,
  повторный call_id в контексте и лишние вызовы отклоняются.
- Лимит стадии:24 dispatched tool calls,24 Responses calls,900s,
  request180s,16000 output tokens. Память и доступные capabilities не расширяются.
  Каждый вызов в batch проходит прежние проверки брокера. Ничего не выполняется
  параллельно; publish не даёт права обойти следующий capability check.
- HTTPS adapter сохраняет точные байты полного parsed response после проверок
  отсутствия credential, но ДО проверки model/protocol/status. Отклонённые
  валидные JSON-ответы тоже сохраняются, вместе с fixed validation reason.
  Malformed JSON не сохраняется в raw artifact. Ошибка локальной записи не
  вызывает повтор уже отправленного запроса. Plain/JSON-escaped credential echo
  не попадает в response artifact. Тела копируются в immutable stage manifest;
  replay сверяет raw и canonical JSON SHA с transport ledger.

## Непрерывность и честность сравнения

Исходный PLAN.json остаётся неизменным. Append-only amendment ссылается на
parent plan/binding SHA, source hashes, неизменный image, первый незавершённый
assignment и SHA всех прежних receipts. Модель, миры, порядок, треки и условия
не меняются. Новый transport ledger не снимает старый cooldown и не допускает
pending/orphan requests. Receipt каждого нового результата содержит execution binding.

Первый pilot-001/world321/F1/natural остаётся неудачным исходом protocol v1.
Следующий assignment — pilot-002/world321/F0/controlled; первый не повторяется.
Protocol v1 имеет сохранённые точные instruction bytes и прежний single-call
validator. Старый raw replay не превращается в успешный вследствие новой схемы.
Смешанные версии в calibration анализируются раздельно; это ещё не heldout.

Worker уже имел последовательный for-loop по calls. Его код и pinned Docker image
не изменены; поправлены host pending queue и независимая реконструкция history.
Fresh context, network-none, read-only mounts и отсутствие API_KEY у worker сохраняются.

## Проверки

186 E009 unit tests прошли. После дополнительной проверки границ amendment и
SHA копируемого body повторены12 live-wrapper tests и затронутый Docker/MCP gate.
Gate включает F1 positive, F0 capability rejection внутри batch, duplicate-ID
failure с сохранённым отклонённым body и tool budget stop. В положительных
scripted случаях BRI=1; в отрицательных BRI=0. Это fixture, НЕ результат LLM.
Rebound manifest не скрывает мутацию retained body — независимый replay отвергает её.

Реальный diagnostic response: v1 отклоняет3 calls, v2 принимает все в исходном
порядке, не меняя ни одного output item. Прежние55 raw files первого пилота
повторно проверены read-only: score и исходы прежние. IDE не сообщила ошибок.

Каталог доказательств:
`C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e009-001\amendment-001`.
Сначала freeze amendment, затем возобновление следующих назначений и raw replay.
Результаты моделей, расходы и новые ограничения фиксируются отдельными receipts;
этот документ не предполагает их успеха. Финальная предрегистрация, обе T2-линии,
heldout, robustness и итоговый научный отчёт по-прежнему впереди.
