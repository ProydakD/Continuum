# E008 — полные таблицы принятого итогового анализа

Источник: `E008-FINAL-EVALUATION-002.json`, SHA-256 `e50c6a3ff3a43a82885da6a57b5807cc7b34036571b6b1668ec8d8724f98174a`.
Все значения скопированы из принятого расчёта без отбора благоприятных исходов.
Машиночитаемые поля, точные значения, все world cells и все reliability bins: `E008-RESULTS.json`.
Округление таблиц — до шести значащих цифр. `—` означает недоступную оценку, не ноль.

## A. Все восемь зарегистрированных контрастов

Разности — доли правильных новых Q; 95% CI — описательный world bootstrap.
| Контраст | Разность | 95% CI | Exact p | Holm p | Положительный критерий |
|---|---:|---|---:|---:|---|
| T1-C1 | -0.260833 | [-0.341667; -0.180833] | 1.50292e-07 | 6.01169e-07 | нет |
| T2-T1 | 0.230833 | [0.148333; 0.315] | 1.71872e-06 | 5.15616e-06 | да |
| C1-C0 | 0.633333 | [0.560833; 0.700833] | 1.85615e-16 | 1.29931e-15 | да |
| C1-SINGLE-A | 0.354167 | [0.294167; 0.410833] | 1.05676e-13 | 6.34055e-13 | да |
| C1-SINGLE-B | 0.6375 | [0.558333; 0.714167] | 9.88792e-17 | 7.91034e-16 | да |
| C1-FULL-JOURNAL | -0.055 | [-0.109167; -0.0075] | 0.0468597 | 0.0468597 | нет |
| T1-FULL-JOURNAL | -0.315833 | [-0.393333; -0.24] | 1.16415e-10 | 5.82077e-10 | нет |
| T2-FULL-JOURNAL | -0.085 | [-0.12625; -0.0475] | 8.45194e-05 | 0.000169039 | нет |

## B. Все условные показатели пересмотра

Ключ группы: phase / condition / control / stage. Natural и deliberate injection не смешиваются.
Среднее и CI усредняются по подходящим мирам; n/d — описательные суммарные события, не независимое n.
0/0 — нет наблюдаемой возможности, а не нулевая способность. Миров без возможности указано отдельно.
| Группа | Происхождение | Метрика | n/d | Миры | Без возможностей | Среднее | 95% CI |
|---|---|---|---:|---:|---:|---:|---|
| robustness / C1 / authentication_ablation / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | natural | false_corrections | 1/57 | 12 | 0 | 0.0208333 | [0; 0.0625] |
| robustness / C1 / authentication_ablation / B | natural | uncertainty_resolutions | 15/15 | 9 | 3 | 1 | [1; 1] |
| robustness / C1 / authentication_ablation / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | natural | claim_error_corrections | 0/1 | 1 | 11 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | natural | false_corrections | 0/58 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / C | natural | uncertainty_resolutions | 13/13 | 6 | 6 | 1 | [1; 1] |
| robustness / C1 / authentication_ablation / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | natural | false_corrections | 0/66 | 11 | 1 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / authentication_ablation / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | natural | claim_error_corrections | 0/1 | 1 | 11 | 0 | [0; 0] |
| robustness / C1 / crash / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | natural | false_corrections | 0/58 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / crash / C | natural | uncertainty_resolutions | 0/13 | 6 | 6 | 0 | [0; 0] |
| robustness / C1 / crash / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | natural | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / crash / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | natural | false_corrections | 0/72 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / cross_model / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / cross_model / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / B | natural | false_corrections | 1/57 | 12 | 0 | 0.0208333 | [0; 0.0625] |
| robustness / C1 / deliberate_false_claim / B | natural | uncertainty_resolutions | 15/15 | 9 | 3 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / B | deliberate_injection | root_rejections | 2/12 | 12 | 0 | 0.166667 | [0; 0.416667] |
| robustness / C1 / deliberate_false_claim / B | deliberate_injection | claim_error_corrections | 17/17 | 10 | 2 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / B | deliberate_injection | dependent_corrections | 4/17 | 10 | 2 | 0.2 | [0; 0.4] |
| robustness / C1 / deliberate_false_claim / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | natural | root_rejections | 0/13 | 8 | 4 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / C | natural | claim_error_corrections | 1/1 | 1 | 11 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | natural | false_corrections | 0/58 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / C | natural | uncertainty_resolutions | 13/13 | 6 | 6 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | natural | false_corrections | 0/72 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / deliberate_false_claim / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | natural | false_corrections | 1/57 | 12 | 0 | 0.0208333 | [0; 0.0625] |
| robustness / C1 / forged_source / B | natural | uncertainty_resolutions | 15/15 | 9 | 3 | 1 | [1; 1] |
| robustness / C1 / forged_source / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | natural | claim_error_corrections | 1/1 | 1 | 11 | 1 | [1; 1] |
| robustness / C1 / forged_source / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | natural | false_corrections | 0/58 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / forged_source / C | natural | uncertainty_resolutions | 13/13 | 6 | 6 | 1 | [1; 1] |
| robustness / C1 / forged_source / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | natural | false_corrections | 0/72 | 12 | 0 | 0 | [0; 0] |
| robustness / C1 / forged_source / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / C1 / forged_source / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | natural | false_corrections | 1/50 | 11 | 1 | 0.0227273 | [0; 0.0681818] |
| robustness / T1 / authentication_ablation / B | natural | uncertainty_resolutions | 16/16 | 9 | 3 | 1 | [1; 1] |
| robustness / T1 / authentication_ablation / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | natural | claim_error_corrections | 1/1 | 1 | 11 | 1 | [1; 1] |
| robustness / T1 / authentication_ablation / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | natural | false_corrections | 0/53 | 11 | 1 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / C | natural | uncertainty_resolutions | 9/12 | 5 | 7 | 0.8 | [0.6; 1] |
| robustness / T1 / authentication_ablation / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | natural | false_corrections | 0/54 | 9 | 3 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / authentication_ablation / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | natural | claim_error_corrections | 0/1 | 1 | 11 | 0 | [0; 0] |
| robustness / T1 / crash / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | natural | false_corrections | 0/47 | 10 | 2 | 0 | [0; 0] |
| robustness / T1 / crash / C | natural | uncertainty_resolutions | 1/12 | 5 | 7 | 0.2 | [0; 0.6] |
| robustness / T1 / crash / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | natural | false_corrections | 0/12 | 2 | 10 | 0 | [0; 0] |
| robustness / T1 / crash / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / crash / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | natural | false_corrections | 0/54 | 9 | 3 | 0 | [0; 0] |
| robustness / T1 / cross_model / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / cross_model / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / B | natural | false_corrections | 1/50 | 11 | 1 | 0.0227273 | [0; 0.0681818] |
| robustness / T1 / deliberate_false_claim / B | natural | uncertainty_resolutions | 16/16 | 9 | 3 | 1 | [1; 1] |
| robustness / T1 / deliberate_false_claim / B | deliberate_injection | root_rejections | 1/12 | 12 | 0 | 0.0833333 | [0; 0.25] |
| robustness / T1 / deliberate_false_claim / B | deliberate_injection | claim_error_corrections | 13/17 | 10 | 2 | 0.7 | [0.5; 0.9] |
| robustness / T1 / deliberate_false_claim / B | deliberate_injection | dependent_corrections | 2/17 | 10 | 2 | 0.1 | [0; 0.3] |
| robustness / T1 / deliberate_false_claim / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | natural | claim_error_corrections | 0/1 | 1 | 11 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | natural | false_corrections | 0/53 | 11 | 1 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / C | natural | uncertainty_resolutions | 8/12 | 5 | 7 | 0.8 | [0.6; 1] |
| robustness / T1 / deliberate_false_claim / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | natural | false_corrections | 0/48 | 8 | 4 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / deliberate_false_claim / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | natural | false_corrections | 1/50 | 11 | 1 | 0.0227273 | [0; 0.0681818] |
| robustness / T1 / forged_source / B | natural | uncertainty_resolutions | 16/16 | 9 | 3 | 1 | [1; 1] |
| robustness / T1 / forged_source / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | natural | claim_error_corrections | 1/1 | 1 | 11 | 1 | [1; 1] |
| robustness / T1 / forged_source / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | natural | false_corrections | 0/53 | 11 | 1 | 0 | [0; 0] |
| robustness / T1 / forged_source / C | natural | uncertainty_resolutions | 7/12 | 5 | 7 | 0.6 | [0.2; 1] |
| robustness / T1 / forged_source / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | natural | false_corrections | 0/54 | 9 | 3 | 0 | [0; 0] |
| robustness / T1 / forged_source / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T1 / forged_source / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | natural | false_corrections | 0/106 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / B | natural | uncertainty_resolutions | 32/32 | 10 | 2 | 1 | [1; 1] |
| robustness / T2 / authentication_ablation / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | natural | false_corrections | 0/111 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / C | natural | uncertainty_resolutions | 27/27 | 7 | 5 | 1 | [1; 1] |
| robustness / T2 / authentication_ablation / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | natural | false_corrections | 0/138 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / authentication_ablation / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | natural | false_corrections | 0/111 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / crash / C | natural | uncertainty_resolutions | 0/27 | 7 | 5 | 0 | [0; 0] |
| robustness / T2 / crash / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | natural | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / crash / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | natural | false_corrections | 0/132 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / cross_model / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / cross_model / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / B | natural | false_corrections | 0/106 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / B | natural | uncertainty_resolutions | 31/32 | 10 | 2 | 0.95 | [0.85; 1] |
| robustness / T2 / deliberate_false_claim / B | deliberate_injection | root_rejections | 4/24 | 12 | 0 | 0.166667 | [0.0416667; 0.291667] |
| robustness / T2 / deliberate_false_claim / B | deliberate_injection | claim_error_corrections | 29/34 | 10 | 2 | 0.85 | [0.75; 0.95] |
| robustness / T2 / deliberate_false_claim / B | deliberate_injection | dependent_corrections | 6/34 | 10 | 2 | 0.2 | [0.1; 0.3] |
| robustness / T2 / deliberate_false_claim / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | natural | root_rejections | 0/14 | 9 | 3 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / C | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | natural | false_corrections | 0/106 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / C | natural | uncertainty_resolutions | 26/26 | 7 | 5 | 1 | [1; 1] |
| robustness / T2 / deliberate_false_claim / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | natural | false_corrections | 0/132 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / deliberate_false_claim / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | natural | false_corrections | 0/106 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / forged_source / B | natural | uncertainty_resolutions | 32/32 | 10 | 2 | 1 | [1; 1] |
| robustness / T2 / forged_source / B | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | natural | false_corrections | 0/111 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / forged_source / C | natural | uncertainty_resolutions | 23/27 | 7 | 5 | 0.928571 | [0.785714; 1] |
| robustness / T2 / forged_source / C | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | natural | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | natural | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | natural | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | natural | false_corrections | 0/132 | 12 | 0 | 0 | [0; 0] |
| robustness / T2 / forged_source / D | natural | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | deliberate_injection | root_rejections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | deliberate_injection | false_corrections | 0/0 | 0 | 12 | — | — |
| robustness / T2 / forged_source / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 12 | — | — |
| test / C0 / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C0 / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / A | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | natural | false_corrections | 5/561 | 59 | 1 | 0.00833333 | [0.00169492; 0.0172316] |
| test / C1 / main / B | natural | uncertainty_resolutions | 126/128 | 41 | 19 | 0.987805 | [0.963415; 1] |
| test / C1 / main / B | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | natural | claim_error_corrections | 2/2 | 2 | 58 | 1 | [1; 1] |
| test / C1 / main / C | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | natural | false_corrections | 4/535 | 59 | 1 | 0.00564972 | [0; 0.0169492] |
| test / C1 / main / C | natural | uncertainty_resolutions | 137/138 | 45 | 15 | 0.994444 | [0.983333; 1] |
| test / C1 / main / C | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | natural | claim_error_corrections | 0/1 | 1 | 59 | 0 | [0; 0] |
| test / C1 / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | natural | false_corrections | 0/670 | 59 | 1 | 0 | [0; 0] |
| test / C1 / main / D | natural | uncertainty_resolutions | 0/4 | 1 | 59 | 0 | [0; 0] |
| test / C1 / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / C1 / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / FULL-JOURNAL / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-A / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / SINGLE-B / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / A | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | natural | claim_error_corrections | 1/1 | 1 | 59 | 1 | [1; 1] |
| test / T1 / main / B | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | natural | false_corrections | 7/553 | 60 | 0 | 0.0109722 | [0.00166667; 0.025] |
| test / T1 / main / B | natural | uncertainty_resolutions | 124/126 | 42 | 18 | 0.988095 | [0.964286; 1] |
| test / T1 / main / B | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | natural | claim_error_corrections | 1/1 | 1 | 59 | 1 | [1; 1] |
| test / T1 / main / C | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | natural | false_corrections | 0/535 | 60 | 0 | 0 | [0; 0] |
| test / T1 / main / C | natural | uncertainty_resolutions | 104/137 | 44 | 16 | 0.801136 | [0.698864; 0.892045] |
| test / T1 / main / C | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | natural | claim_error_corrections | 0/1 | 1 | 59 | 0 | [0; 0] |
| test / T1 / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | natural | false_corrections | 0/653 | 60 | 0 | 0 | [0; 0] |
| test / T1 / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T1 / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | natural | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / A | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | natural | false_corrections | 2/1084 | 60 | 0 | 0.00173611 | [0; 0.00451389] |
| test / T2 / main / B | natural | uncertainty_resolutions | 256/259 | 43 | 17 | 0.985465 | [0.968023; 1] |
| test / T2 / main / B | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / B | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | natural | claim_error_corrections | 2/2 | 1 | 59 | 1 | [1; 1] |
| test / T2 / main / C | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | natural | false_corrections | 0/1050 | 60 | 0 | 0 | [0; 0] |
| test / T2 / main / C | natural | uncertainty_resolutions | 270/274 | 45 | 15 | 0.981481 | [0.959259; 1] |
| test / T2 / main / C | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / C | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | natural | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | natural | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | natural | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | natural | false_corrections | 0/1308 | 60 | 0 | 0 | [0; 0] |
| test / T2 / main / D | natural | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | deliberate_injection | root_rejections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | deliberate_injection | claim_error_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | deliberate_injection | dependent_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | deliberate_injection | false_corrections | 0/0 | 0 | 60 | — | — |
| test / T2 / main / D | deliberate_injection | uncertainty_resolutions | 0/0 | 0 | 60 | — | — |

## C. Наблюдаемость, уверенность, объяснения и происхождение

Показатели относятся ко всем назначенным P+Q в группе, не только к новым Q.
Brier — условно по валидным ответам; отсутствие ответа не считается прекрасной калибровкой.
| Группа | Контексты | Отказы/непроверенные | Нет наблюдаемого предшественника | Назначено вопросов | Валидных | Правильных null | Избыточных null | Неопределённых point | Уверенных неопределённых point |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| robustness / C1 / authentication_ablation / B | 12 | 0 | 0 | 72 | 72 | 25 | 0 | 1 | 1 |
| robustness / C1 / authentication_ablation / C | 12 | 1 | 0 | 72 | 66 | 11 | 0 | 0 | 0 |
| robustness / C1 / authentication_ablation / D | 12 | 1 | 1 | 192 | 176 | 39 | 0 | 0 | 0 |
| robustness / C1 / crash / C | 12 | 12 | 0 | 72 | 0 | 0 | 0 | 0 | 0 |
| robustness / C1 / crash / D | 12 | 0 | 12 | 192 | 192 | 42 | 0 | 0 | 0 |
| robustness / C1 / cross_model / D | 12 | 0 | 0 | 192 | 192 | 42 | 0 | 0 | 0 |
| robustness / C1 / deliberate_false_claim / B | 12 | 0 | 0 | 72 | 72 | 25 | 0 | 1 | 1 |
| robustness / C1 / deliberate_false_claim / C | 12 | 0 | 0 | 72 | 72 | 12 | 0 | 0 | 0 |
| robustness / C1 / deliberate_false_claim / D | 12 | 0 | 0 | 192 | 192 | 42 | 0 | 0 | 0 |
| robustness / C1 / forged_source / B | 12 | 0 | 0 | 72 | 72 | 25 | 0 | 1 | 1 |
| robustness / C1 / forged_source / C | 12 | 0 | 0 | 72 | 72 | 12 | 0 | 0 | 0 |
| robustness / C1 / forged_source / D | 12 | 0 | 0 | 192 | 192 | 42 | 0 | 0 | 0 |
| robustness / T1 / authentication_ablation / B | 12 | 3 | 1 | 72 | 66 | 24 | 0 | 1 | 1 |
| robustness / T1 / authentication_ablation / C | 12 | 4 | 1 | 72 | 54 | 9 | 0 | 0 | 0 |
| robustness / T1 / authentication_ablation / D | 12 | 4 | 3 | 192 | 128 | 30 | 0 | 0 | 0 |
| robustness / T1 / crash / C | 12 | 12 | 2 | 72 | 12 | 3 | 0 | 0 | 0 |
| robustness / T1 / crash / D | 12 | 5 | 10 | 192 | 112 | 22 | 0 | 0 | 0 |
| robustness / T1 / cross_model / D | 12 | 7 | 3 | 192 | 80 | 16 | 0 | 0 | 0 |
| robustness / T1 / deliberate_false_claim / B | 12 | 4 | 1 | 72 | 66 | 24 | 0 | 1 | 1 |
| robustness / T1 / deliberate_false_claim / C | 12 | 9 | 1 | 72 | 48 | 7 | 0 | 0 | 0 |
| robustness / T1 / deliberate_false_claim / D | 12 | 9 | 4 | 192 | 48 | 13 | 0 | 0 | 0 |
| robustness / T1 / forged_source / B | 12 | 3 | 1 | 72 | 66 | 24 | 0 | 1 | 1 |
| robustness / T1 / forged_source / C | 12 | 6 | 1 | 72 | 54 | 10 | 0 | 0 | 0 |
| robustness / T1 / forged_source / D | 12 | 6 | 3 | 192 | 96 | 23 | 0 | 0 | 0 |
| robustness / T2 / authentication_ablation / B | 24 | 1 | 1 | 144 | 138 | 50 | 0 | 0 | 0 |
| robustness / T2 / authentication_ablation / C | 24 | 1 | 1 | 144 | 138 | 23 | 0 | 0 | 0 |
| robustness / T2 / authentication_ablation / D | 24 | 1 | 1 | 384 | 368 | 81 | 0 | 0 | 0 |
| robustness / T2 / crash / C | 24 | 24 | 1 | 144 | 0 | 0 | 0 | 0 | 0 |
| robustness / T2 / crash / D | 24 | 1 | 24 | 384 | 368 | 81 | 0 | 0 | 0 |
| robustness / T2 / cross_model / D | 24 | 2 | 2 | 384 | 352 | 79 | 0 | 0 | 0 |
| robustness / T2 / deliberate_false_claim / B | 24 | 2 | 1 | 144 | 132 | 49 | 0 | 0 | 0 |
| robustness / T2 / deliberate_false_claim / C | 24 | 2 | 2 | 144 | 132 | 23 | 0 | 0 | 0 |
| robustness / T2 / deliberate_false_claim / D | 24 | 2 | 2 | 384 | 352 | 79 | 0 | 0 | 0 |
| robustness / T2 / forged_source / B | 24 | 1 | 1 | 144 | 138 | 50 | 0 | 0 | 0 |
| robustness / T2 / forged_source / C | 24 | 2 | 1 | 144 | 132 | 23 | 0 | 0 | 0 |
| robustness / T2 / forged_source / D | 24 | 2 | 2 | 384 | 352 | 79 | 0 | 0 | 0 |
| test / C0 / main / D | 120 | 50 | 120 | 1920 | 1120 | 786 | 0 | 4 | 4 |
| test / C1 / main / A | 120 | 5 | 120 | 720 | 690 | 396 | 0 | 4 | 4 |
| test / C1 / main / B | 120 | 7 | 5 | 720 | 678 | 259 | 0 | 6 | 6 |
| test / C1 / main / C | 120 | 7 | 7 | 720 | 678 | 121 | 4 | 3 | 3 |
| test / C1 / main / D | 120 | 7 | 7 | 1920 | 1808 | 407 | 16 | 7 | 7 |
| test / FULL-JOURNAL / main / D | 120 | 1 | 120 | 1920 | 1904 | 420 | 1 | 11 | 11 |
| test / SINGLE-A / main / D | 120 | 6 | 120 | 1920 | 1824 | 1096 | 0 | 41 | 41 |
| test / SINGLE-B / main / D | 120 | 54 | 120 | 1920 | 1056 | 733 | 2 | 9 | 9 |
| test / T1 / main / A | 120 | 6 | 120 | 720 | 684 | 384 | 0 | 9 | 9 |
| test / T1 / main / B | 120 | 11 | 6 | 720 | 678 | 251 | 0 | 10 | 10 |
| test / T1 / main / C | 120 | 40 | 7 | 720 | 654 | 113 | 0 | 0 | 0 |
| test / T1 / main / D | 120 | 40 | 11 | 1920 | 1280 | 292 | 0 | 0 | 0 |
| test / T2 / main / A | 240 | 16 | 240 | 1440 | 1344 | 770 | 0 | 1 | 1 |
| test / T2 / main / B | 240 | 19 | 16 | 1440 | 1326 | 500 | 0 | 3 | 3 |
| test / T2 / main / C | 240 | 22 | 19 | 1440 | 1308 | 225 | 0 | 0 | 0 |
| test / T2 / main / D | 240 | 24 | 22 | 3840 | 3456 | 770 | 1 | 4 | 4 |

| Группа | Метрика | Миры | Среднее | 95% CI |
|---|---|---:|---:|---|
| robustness / C1 / authentication_ablation / B | supported_explanations | 12 | 0.638889 | [0.541667; 0.75] |
| robustness / C1 / authentication_ablation / B | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / authentication_ablation / B | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / authentication_ablation / B | brier_sum | 12 | 0.0139653 | [6.25e-05; 0.0417278] |
| robustness / C1 / authentication_ablation / B | correct_abstentions | 11 | 0.954545 | [0.863636; 1] |
| robustness / C1 / authentication_ablation / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / C1 / authentication_ablation / C | supported_explanations | 12 | 0.763889 | [0.625; 0.875] |
| robustness / C1 / authentication_ablation / C | source_ids_valid | 12 | 0.916667 | [0.75; 1] |
| robustness / C1 / authentication_ablation / C | valid_answers | 12 | 0.916667 | [0.75; 1] |
| robustness / C1 / authentication_ablation / C | brier_sum | 11 | 8.0303e-05 | [5.90909e-05; 0.0001] |
| robustness / C1 / authentication_ablation / C | correct_abstentions | 8 | 0.875 | [0.625; 1] |
| robustness / C1 / authentication_ablation / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / D | supported_explanations | 12 | 0.697917 | [0.572917; 0.796875] |
| robustness / C1 / authentication_ablation / D | source_ids_valid | 12 | 0.916667 | [0.75; 1] |
| robustness / C1 / authentication_ablation / D | valid_answers | 12 | 0.916667 | [0.75; 1] |
| robustness / C1 / authentication_ablation / D | brier_sum | 11 | 9.71591e-05 | [9.48864e-05; 9.94318e-05] |
| robustness / C1 / authentication_ablation / D | correct_abstentions | 12 | 0.916667 | [0.75; 1] |
| robustness / C1 / authentication_ablation / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / authentication_ablation / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / C1 / crash / C | supported_explanations | 12 | 0 | [0; 0] |
| robustness / C1 / crash / C | source_ids_valid | 12 | 0 | [0; 0] |
| robustness / C1 / crash / C | valid_answers | 12 | 0 | [0; 0] |
| robustness / C1 / crash / C | brier_sum | 0 | — | — |
| robustness / C1 / crash / C | correct_abstentions | 8 | 0 | [0; 0] |
| robustness / C1 / crash / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / crash / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / C1 / crash / D | supported_explanations | 12 | 0.765625 | [0.713542; 0.817708] |
| robustness / C1 / crash / D | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / crash / D | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / crash / D | brier_sum | 12 | 6.25e-06 | [0; 1.875e-05] |
| robustness / C1 / crash / D | correct_abstentions | 12 | 1 | [1; 1] |
| robustness / C1 / crash / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / crash / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / C1 / cross_model / D | supported_explanations | 12 | 0.765625 | [0.713542; 0.817708] |
| robustness / C1 / cross_model / D | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / cross_model / D | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / cross_model / D | brier_sum | 12 | 6.25e-06 | [0; 1.875e-05] |
| robustness / C1 / cross_model / D | correct_abstentions | 12 | 1 | [1; 1] |
| robustness / C1 / cross_model / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / cross_model / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / B | supported_explanations | 12 | 0.902778 | [0.791667; 0.986111] |
| robustness / C1 / deliberate_false_claim / B | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / B | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / B | brier_sum | 12 | 0.0139028 | [5.55556e-06; 0.0416722] |
| robustness / C1 / deliberate_false_claim / B | correct_abstentions | 11 | 0.954545 | [0.863636; 1] |
| robustness / C1 / deliberate_false_claim / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / C1 / deliberate_false_claim / C | supported_explanations | 12 | 0.833333 | [0.763889; 0.902778] |
| robustness / C1 / deliberate_false_claim / C | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / C | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / C | brier_sum | 12 | 8.375e-06 | [0; 2.5e-05] |
| robustness / C1 / deliberate_false_claim / C | correct_abstentions | 8 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / D | supported_explanations | 12 | 0.78125 | [0.744792; 0.817708] |
| robustness / C1 / deliberate_false_claim / D | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / D | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / D | brier_sum | 12 | 6.77083e-06 | [0; 2.03125e-05] |
| robustness / C1 / deliberate_false_claim / D | correct_abstentions | 12 | 1 | [1; 1] |
| robustness / C1 / deliberate_false_claim / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / deliberate_false_claim / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / C1 / forged_source / B | supported_explanations | 12 | 0.638889 | [0.541667; 0.75] |
| robustness / C1 / forged_source / B | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / B | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / B | brier_sum | 12 | 0.0138958 | [0; 0.0416736] |
| robustness / C1 / forged_source / B | correct_abstentions | 11 | 0.954545 | [0.863636; 1] |
| robustness / C1 / forged_source / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / forged_source / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / C1 / forged_source / C | supported_explanations | 12 | 0.833333 | [0.763889; 0.902778] |
| robustness / C1 / forged_source / C | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / C | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / C | brier_sum | 12 | 5.55556e-08 | [0; 1.66667e-07] |
| robustness / C1 / forged_source / C | correct_abstentions | 8 | 1 | [1; 1] |
| robustness / C1 / forged_source / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / forged_source / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / C1 / forged_source / D | supported_explanations | 12 | 0.78125 | [0.744792; 0.817708] |
| robustness / C1 / forged_source / D | source_ids_valid | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / D | valid_answers | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / D | brier_sum | 12 | 6.25e-08 | [0; 1.875e-07] |
| robustness / C1 / forged_source / D | correct_abstentions | 12 | 1 | [1; 1] |
| robustness / C1 / forged_source / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / C1 / forged_source / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / B | supported_explanations | 12 | 0.569444 | [0.458333; 0.708333] |
| robustness / T1 / authentication_ablation / B | source_ids_valid | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / authentication_ablation / B | valid_answers | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / authentication_ablation / B | brier_sum | 11 | 0.0151515 | [0; 0.0454545] |
| robustness / T1 / authentication_ablation / B | correct_abstentions | 11 | 0.863636 | [0.681818; 1] |
| robustness / T1 / authentication_ablation / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / T1 / authentication_ablation / C | supported_explanations | 12 | 0.625 | [0.416667; 0.819444] |
| robustness / T1 / authentication_ablation / C | source_ids_valid | 12 | 0.75 | [0.5; 0.916667] |
| robustness / T1 / authentication_ablation / C | valid_answers | 12 | 0.75 | [0.5; 0.916667] |
| robustness / T1 / authentication_ablation / C | brier_sum | 9 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / C | correct_abstentions | 8 | 0.875 | [0.625; 1] |
| robustness / T1 / authentication_ablation / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / D | supported_explanations | 12 | 0.510417 | [0.354167; 0.666667] |
| robustness / T1 / authentication_ablation / D | source_ids_valid | 12 | 0.666667 | [0.5; 0.833333] |
| robustness / T1 / authentication_ablation / D | valid_answers | 12 | 0.666667 | [0.5; 0.833333] |
| robustness / T1 / authentication_ablation / D | brier_sum | 8 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / D | correct_abstentions | 12 | 0.666667 | [0.5; 0.833333] |
| robustness / T1 / authentication_ablation / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / authentication_ablation / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T1 / crash / C | supported_explanations | 12 | 0.125 | [0; 0.305556] |
| robustness / T1 / crash / C | source_ids_valid | 12 | 0.166667 | [0; 0.416667] |
| robustness / T1 / crash / C | valid_answers | 12 | 0.166667 | [0; 0.416667] |
| robustness / T1 / crash / C | brier_sum | 2 | 0 | [0; 0] |
| robustness / T1 / crash / C | correct_abstentions | 8 | 0.25 | [0; 0.625] |
| robustness / T1 / crash / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / crash / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T1 / crash / D | supported_explanations | 12 | 0.46875 | [0.265625; 0.666667] |
| robustness / T1 / crash / D | source_ids_valid | 12 | 0.583333 | [0.333333; 0.833333] |
| robustness / T1 / crash / D | valid_answers | 12 | 0.583333 | [0.333333; 0.833333] |
| robustness / T1 / crash / D | brier_sum | 7 | 0 | [0; 0] |
| robustness / T1 / crash / D | correct_abstentions | 12 | 0.583333 | [0.333333; 0.833333] |
| robustness / T1 / crash / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / crash / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T1 / cross_model / D | supported_explanations | 12 | 0.333333 | [0.140625; 0.494792] |
| robustness / T1 / cross_model / D | source_ids_valid | 12 | 0.416667 | [0.166667; 0.583333] |
| robustness / T1 / cross_model / D | valid_answers | 12 | 0.416667 | [0.166667; 0.583333] |
| robustness / T1 / cross_model / D | brier_sum | 5 | 0 | [0; 0] |
| robustness / T1 / cross_model / D | correct_abstentions | 12 | 0.416667 | [0.166667; 0.583333] |
| robustness / T1 / cross_model / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / cross_model / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / B | supported_explanations | 12 | 0.569444 | [0.458333; 0.708333] |
| robustness / T1 / deliberate_false_claim / B | source_ids_valid | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / deliberate_false_claim / B | valid_answers | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / deliberate_false_claim / B | brier_sum | 11 | 0.0151515 | [0; 0.0454545] |
| robustness / T1 / deliberate_false_claim / B | correct_abstentions | 11 | 0.863636 | [0.681818; 1] |
| robustness / T1 / deliberate_false_claim / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / T1 / deliberate_false_claim / C | supported_explanations | 12 | 0.569444 | [0.333333; 0.777778] |
| robustness / T1 / deliberate_false_claim / C | source_ids_valid | 12 | 0.666667 | [0.416667; 0.916667] |
| robustness / T1 / deliberate_false_claim / C | valid_answers | 12 | 0.666667 | [0.416667; 0.916667] |
| robustness / T1 / deliberate_false_claim / C | brier_sum | 8 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / C | correct_abstentions | 8 | 0.625 | [0.25; 0.875] |
| robustness / T1 / deliberate_false_claim / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / D | supported_explanations | 12 | 0.182292 | [0.0520833; 0.364583] |
| robustness / T1 / deliberate_false_claim / D | source_ids_valid | 12 | 0.25 | [0.0833333; 0.5] |
| robustness / T1 / deliberate_false_claim / D | valid_answers | 12 | 0.25 | [0.0833333; 0.5] |
| robustness / T1 / deliberate_false_claim / D | brier_sum | 3 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / D | correct_abstentions | 12 | 0.25 | [0.0833333; 0.5] |
| robustness / T1 / deliberate_false_claim / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / deliberate_false_claim / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T1 / forged_source / B | supported_explanations | 12 | 0.569444 | [0.458333; 0.708333] |
| robustness / T1 / forged_source / B | source_ids_valid | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / forged_source / B | valid_answers | 12 | 0.916667 | [0.75; 1] |
| robustness / T1 / forged_source / B | brier_sum | 11 | 0.0151515 | [0; 0.0454545] |
| robustness / T1 / forged_source / B | correct_abstentions | 11 | 0.863636 | [0.681818; 1] |
| robustness / T1 / forged_source / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / forged_source / B | high_confidence_unsupported_points | 11 | 0.0454545 | [0; 0.136364] |
| robustness / T1 / forged_source / C | supported_explanations | 12 | 0.611111 | [0.416667; 0.805556] |
| robustness / T1 / forged_source / C | source_ids_valid | 12 | 0.75 | [0.5; 0.916667] |
| robustness / T1 / forged_source / C | valid_answers | 12 | 0.75 | [0.5; 0.916667] |
| robustness / T1 / forged_source / C | brier_sum | 9 | 7.40741e-06 | [0; 1.48148e-05] |
| robustness / T1 / forged_source / C | correct_abstentions | 8 | 0.875 | [0.625; 1] |
| robustness / T1 / forged_source / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / forged_source / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T1 / forged_source / D | supported_explanations | 12 | 0.380208 | [0.239583; 0.557292] |
| robustness / T1 / forged_source / D | source_ids_valid | 12 | 0.5 | [0.333333; 0.75] |
| robustness / T1 / forged_source / D | valid_answers | 12 | 0.5 | [0.333333; 0.75] |
| robustness / T1 / forged_source / D | brier_sum | 6 | 0 | [0; 0] |
| robustness / T1 / forged_source / D | correct_abstentions | 12 | 0.5 | [0.333333; 0.75] |
| robustness / T1 / forged_source / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T1 / forged_source / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / B | supported_explanations | 12 | 0.611111 | [0.486111; 0.736111] |
| robustness / T2 / authentication_ablation / B | source_ids_valid | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / B | valid_answers | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / B | brier_sum | 12 | 7.01806e-05 | [5.28194e-05; 8.75e-05] |
| robustness / T2 / authentication_ablation / B | correct_abstentions | 11 | 0.954545 | [0.863636; 1] |
| robustness / T2 / authentication_ablation / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / B | high_confidence_unsupported_points | 11 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / C | supported_explanations | 12 | 0.798611 | [0.708333; 0.881944] |
| robustness / T2 / authentication_ablation / C | source_ids_valid | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / C | valid_answers | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / C | brier_sum | 12 | 6.94861e-05 | [5.35972e-05; 8.54167e-05] |
| robustness / T2 / authentication_ablation / C | correct_abstentions | 8 | 0.9375 | [0.8125; 1] |
| robustness / T2 / authentication_ablation / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / D | supported_explanations | 12 | 0.747396 | [0.690104; 0.802083] |
| robustness / T2 / authentication_ablation / D | source_ids_valid | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / D | valid_answers | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / D | brier_sum | 12 | 7.08438e-05 | [6.09375e-05; 7.91771e-05] |
| robustness / T2 / authentication_ablation / D | correct_abstentions | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / authentication_ablation / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / authentication_ablation / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T2 / crash / C | supported_explanations | 12 | 0 | [0; 0] |
| robustness / T2 / crash / C | source_ids_valid | 12 | 0 | [0; 0] |
| robustness / T2 / crash / C | valid_answers | 12 | 0 | [0; 0] |
| robustness / T2 / crash / C | brier_sum | 0 | — | — |
| robustness / T2 / crash / C | correct_abstentions | 8 | 0 | [0; 0] |
| robustness / T2 / crash / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / crash / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T2 / crash / D | supported_explanations | 12 | 0.747396 | [0.690104; 0.802083] |
| robustness / T2 / crash / D | source_ids_valid | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / crash / D | valid_answers | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / crash / D | brier_sum | 12 | 6.13021e-06 | [1.5625e-07; 1.41302e-05] |
| robustness / T2 / crash / D | correct_abstentions | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / crash / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / crash / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T2 / cross_model / D | supported_explanations | 12 | 0.710938 | [0.625; 0.786458] |
| robustness / T2 / cross_model / D | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / cross_model / D | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / cross_model / D | brier_sum | 12 | 6.25e-08 | [0; 1.25e-07] |
| robustness / T2 / cross_model / D | correct_abstentions | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / cross_model / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / cross_model / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / B | supported_explanations | 12 | 0.743056 | [0.618056; 0.861111] |
| robustness / T2 / deliberate_false_claim / B | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / B | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / B | brier_sum | 12 | 4.22917e-06 | [4.16667e-08; 1.25208e-05] |
| robustness / T2 / deliberate_false_claim / B | correct_abstentions | 11 | 0.909091 | [0.772727; 1] |
| robustness / T2 / deliberate_false_claim / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / B | high_confidence_unsupported_points | 11 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / C | supported_explanations | 12 | 0.756944 | [0.645833; 0.861111] |
| robustness / T2 / deliberate_false_claim / C | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / C | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / C | brier_sum | 12 | 4.20833e-06 | [2.08333e-08; 1.25417e-05] |
| robustness / T2 / deliberate_false_claim / C | correct_abstentions | 8 | 0.9375 | [0.8125; 1] |
| robustness / T2 / deliberate_false_claim / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / D | supported_explanations | 12 | 0.710938 | [0.625; 0.786458] |
| robustness / T2 / deliberate_false_claim / D | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / D | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / D | brier_sum | 12 | 1.38021e-05 | [3.38542e-06; 2.36979e-05] |
| robustness / T2 / deliberate_false_claim / D | correct_abstentions | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / deliberate_false_claim / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / deliberate_false_claim / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| robustness / T2 / forged_source / B | supported_explanations | 12 | 0.611111 | [0.486111; 0.736111] |
| robustness / T2 / forged_source / B | source_ids_valid | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / forged_source / B | valid_answers | 12 | 0.958333 | [0.875; 1] |
| robustness / T2 / forged_source / B | brier_sum | 12 | 9.80556e-06 | [2.20833e-06; 1.94861e-05] |
| robustness / T2 / forged_source / B | correct_abstentions | 11 | 0.954545 | [0.863636; 1] |
| robustness / T2 / forged_source / B | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / forged_source / B | high_confidence_unsupported_points | 11 | 0 | [0; 0] |
| robustness / T2 / forged_source / C | supported_explanations | 12 | 0.756944 | [0.645833; 0.861111] |
| robustness / T2 / forged_source / C | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / forged_source / C | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / forged_source / C | brier_sum | 12 | 1.05e-05 | [8.33333e-08; 2.71667e-05] |
| robustness / T2 / forged_source / C | correct_abstentions | 8 | 0.9375 | [0.8125; 1] |
| robustness / T2 / forged_source / C | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / forged_source / C | high_confidence_unsupported_points | 8 | 0 | [0; 0] |
| robustness / T2 / forged_source / D | supported_explanations | 12 | 0.710938 | [0.625; 0.786458] |
| robustness / T2 / forged_source / D | source_ids_valid | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / forged_source / D | valid_answers | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / forged_source / D | brier_sum | 12 | 6.54167e-06 | [3.125e-08; 1.5625e-05] |
| robustness / T2 / forged_source / D | correct_abstentions | 12 | 0.916667 | [0.791667; 1] |
| robustness / T2 / forged_source / D | excess_abstentions | 12 | 0 | [0; 0] |
| robustness / T2 / forged_source / D | high_confidence_unsupported_points | 12 | 0 | [0; 0] |
| test / C0 / main / D | supported_explanations | 60 | 0.171875 | [0.131771; 0.213021] |
| test / C0 / main / D | source_ids_valid | 60 | 0.583333 | [0.483333; 0.675] |
| test / C0 / main / D | valid_answers | 60 | 0.583333 | [0.483333; 0.675] |
| test / C0 / main / D | brier_sum | 47 | 0.00532347 | [1.06383e-06; 0.0159638] |
| test / C0 / main / D | correct_abstentions | 60 | 0.579167 | [0.483333; 0.675] |
| test / C0 / main / D | excess_abstentions | 58 | 0 | [0; 0] |
| test / C0 / main / D | high_confidence_unsupported_points | 60 | 0.00416667 | [0; 0.0125] |
| test / C1 / main / A | supported_explanations | 60 | 0.402778 | [0.3625; 0.443056] |
| test / C1 / main / A | source_ids_valid | 60 | 0.958333 | [0.908333; 0.991667] |
| test / C1 / main / A | valid_answers | 60 | 0.958333 | [0.908333; 0.991667] |
| test / C1 / main / A | brier_sum | 59 | 0.00848008 | [6.07345e-06; 0.0211941] |
| test / C1 / main / A | correct_abstentions | 60 | 0.950139 | [0.900556; 0.988889] |
| test / C1 / main / A | excess_abstentions | 59 | 0 | [0; 0] |
| test / C1 / main / A | high_confidence_unsupported_points | 60 | 0.00819444 | [0; 0.0183333] |
| test / C1 / main / B | supported_explanations | 60 | 0.572222 | [0.520833; 0.623611] |
| test / C1 / main / B | source_ids_valid | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / B | valid_answers | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / B | brier_sum | 59 | 0.00848392 | [0.00142544; 0.0169565] |
| test / C1 / main / B | correct_abstentions | 56 | 0.933036 | [0.888393; 0.96875] |
| test / C1 / main / B | excess_abstentions | 60 | 0 | [0; 0] |
| test / C1 / main / B | high_confidence_unsupported_points | 56 | 0.0223214 | [0.00446429; 0.0401786] |
| test / C1 / main / C | supported_explanations | 60 | 0.761111 | [0.709722; 0.811111] |
| test / C1 / main / C | source_ids_valid | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / C | valid_answers | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / C | brier_sum | 59 | 0.011303 | [0.00141544; 0.0254284] |
| test / C1 / main / C | correct_abstentions | 42 | 0.952381 | [0.904762; 0.988095] |
| test / C1 / main / C | excess_abstentions | 60 | 0.00833333 | [0; 0.025] |
| test / C1 / main / C | high_confidence_unsupported_points | 42 | 0.0238095 | [0; 0.0595238] |
| test / C1 / main / D | supported_explanations | 60 | 0.713542 | [0.671354; 0.751563] |
| test / C1 / main / D | source_ids_valid | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / D | valid_answers | 60 | 0.941667 | [0.891667; 0.983333] |
| test / C1 / main / D | brier_sum | 59 | 0.0137749 | [0.00265133; 0.0296641] |
| test / C1 / main / D | correct_abstentions | 60 | 0.926667 | [0.875; 0.968333] |
| test / C1 / main / D | excess_abstentions | 60 | 0.0112374 | [0; 0.0294192] |
| test / C1 / main / D | high_confidence_unsupported_points | 60 | 0.015 | [0; 0.0383333] |
| test / FULL-JOURNAL / main / D | supported_explanations | 60 | 0.758333 | [0.734375; 0.78125] |
| test / FULL-JOURNAL / main / D | source_ids_valid | 60 | 0.991667 | [0.975; 1] |
| test / FULL-JOURNAL / main / D | valid_answers | 60 | 0.991667 | [0.975; 1] |
| test / FULL-JOURNAL / main / D | brier_sum | 60 | 0.00833469 | [0.00260553; 0.0151048] |
| test / FULL-JOURNAL / main / D | correct_abstentions | 60 | 0.963333 | [0.935556; 0.9875] |
| test / FULL-JOURNAL / main / D | excess_abstentions | 60 | 0.000641026 | [0; 0.00192308] |
| test / FULL-JOURNAL / main / D | high_confidence_unsupported_points | 60 | 0.0283333 | [0.00833333; 0.0525] |
| test / SINGLE-A / main / D | supported_explanations | 60 | 0.357812 | [0.329688; 0.384375] |
| test / SINGLE-A / main / D | source_ids_valid | 60 | 0.95 | [0.9; 0.991667] |
| test / SINGLE-A / main / D | valid_answers | 60 | 0.95 | [0.9; 0.991667] |
| test / SINGLE-A / main / D | brier_sum | 59 | 0.0227754 | [0.0121822; 0.034428] |
| test / SINGLE-A / main / D | correct_abstentions | 60 | 0.916072 | [0.866653; 0.957391] |
| test / SINGLE-A / main / D | excess_abstentions | 60 | 0 | [0; 0] |
| test / SINGLE-A / main / D | high_confidence_unsupported_points | 60 | 0.0339282 | [0.0181265; 0.0514889] |
| test / SINGLE-B / main / D | supported_explanations | 60 | 0.1625 | [0.122396; 0.204167] |
| test / SINGLE-B / main / D | source_ids_valid | 60 | 0.55 | [0.441667; 0.658333] |
| test / SINGLE-B / main / D | valid_answers | 60 | 0.55 | [0.441667; 0.658333] |
| test / SINGLE-B / main / D | brier_sum | 42 | 0.0126552 | [0.00149494; 0.0297667] |
| test / SINGLE-B / main / D | correct_abstentions | 60 | 0.544059 | [0.439744; 0.648386] |
| test / SINGLE-B / main / D | excess_abstentions | 57 | 0.00300752 | [0; 0.00776942] |
| test / SINGLE-B / main / D | high_confidence_unsupported_points | 60 | 0.00594093 | [0; 0.0138164] |
| test / T1 / main / A | supported_explanations | 60 | 0.402778 | [0.3625; 0.441667] |
| test / T1 / main / A | source_ids_valid | 60 | 0.95 | [0.908333; 0.983333] |
| test / T1 / main / A | valid_answers | 60 | 0.95 | [0.908333; 0.983333] |
| test / T1 / main / A | brier_sum | 60 | 0.0138921 | [0.00555625; 0.0250024] |
| test / T1 / main / A | correct_abstentions | 60 | 0.930139 | [0.888472; 0.966111] |
| test / T1 / main / A | excess_abstentions | 59 | 0 | [0; 0] |
| test / T1 / main / A | high_confidence_unsupported_points | 60 | 0.0198611 | [0.00555556; 0.0372222] |
| test / T1 / main / B | supported_explanations | 60 | 0.577778 | [0.526389; 0.630556] |
| test / T1 / main / B | source_ids_valid | 60 | 0.941667 | [0.9; 0.975] |
| test / T1 / main / B | valid_answers | 60 | 0.941667 | [0.9; 0.975] |
| test / T1 / main / B | brier_sum | 60 | 0.0138925 | [0.00278361; 0.0277824] |
| test / T1 / main / B | correct_abstentions | 56 | 0.901786 | [0.852679; 0.946429] |
| test / T1 / main / B | excess_abstentions | 60 | 0 | [0; 0] |
| test / T1 / main / B | high_confidence_unsupported_points | 56 | 0.0357143 | [0.00892857; 0.0669643] |
| test / T1 / main / C | supported_explanations | 60 | 0.745833 | [0.688889; 0.8] |
| test / T1 / main / C | source_ids_valid | 60 | 0.908333 | [0.858333; 0.958333] |
| test / T1 / main / C | valid_answers | 60 | 0.908333 | [0.858333; 0.958333] |
| test / T1 / main / C | brier_sum | 60 | 0.0013925 | [1.52778e-06; 0.00417167] |
| test / T1 / main / C | correct_abstentions | 42 | 0.904762 | [0.845238; 0.964286] |
| test / T1 / main / C | excess_abstentions | 60 | 0 | [0; 0] |
| test / T1 / main / C | high_confidence_unsupported_points | 42 | 0 | [0; 0] |
| test / T1 / main / D | supported_explanations | 60 | 0.508854 | [0.447917; 0.56875] |
| test / T1 / main / D | source_ids_valid | 60 | 0.666667 | [0.591667; 0.741667] |
| test / T1 / main / D | valid_answers | 60 | 0.666667 | [0.591667; 0.741667] |
| test / T1 / main / D | brier_sum | 55 | 0.00170761 | [1.59091e-06; 0.00454773] |
| test / T1 / main / D | correct_abstentions | 60 | 0.666667 | [0.591667; 0.741667] |
| test / T1 / main / D | excess_abstentions | 60 | 0 | [0; 0] |
| test / T1 / main / D | high_confidence_unsupported_points | 60 | 0 | [0; 0] |
| test / T2 / main / A | supported_explanations | 60 | 0.397917 | [0.359028; 0.436806] |
| test / T2 / main / A | source_ids_valid | 60 | 0.933333 | [0.9; 0.9625] |
| test / T2 / main / A | valid_answers | 60 | 0.933333 | [0.9; 0.9625] |
| test / T2 / main / A | brier_sum | 60 | 0.000697584 | [1.79051e-06; 0.00208755] |
| test / T2 / main / A | correct_abstentions | 60 | 0.931944 | [0.9; 0.961111] |
| test / T2 / main / A | excess_abstentions | 59 | 0 | [0; 0] |
| test / T2 / main / A | high_confidence_unsupported_points | 60 | 0.00138889 | [0; 0.00416667] |
| test / T2 / main / B | supported_explanations | 60 | 0.570833 | [0.521528; 0.622222] |
| test / T2 / main / B | source_ids_valid | 60 | 0.920833 | [0.8875; 0.95] |
| test / T2 / main / B | valid_answers | 60 | 0.920833 | [0.8875; 0.95] |
| test / T2 / main / B | brier_sum | 60 | 0.00275851 | [8.49745e-06; 0.00620454] |
| test / T2 / main / B | correct_abstentions | 56 | 0.91183 | [0.878348; 0.944196] |
| test / T2 / main / B | excess_abstentions | 60 | 0 | [0; 0] |
| test / T2 / main / B | high_confidence_unsupported_points | 56 | 0.0078125 | [0; 0.0189732] |
| test / T2 / main / C | supported_explanations | 60 | 0.752083 | [0.702778; 0.800694] |
| test / T2 / main / C | source_ids_valid | 60 | 0.908333 | [0.870833; 0.941667] |
| test / T2 / main / C | valid_answers | 60 | 0.908333 | [0.870833; 0.941667] |
| test / T2 / main / C | brier_sum | 60 | 8.29005e-06 | [4.81042e-06; 1.21688e-05] |
| test / T2 / main / C | correct_abstentions | 42 | 0.892857 | [0.845238; 0.934524] |
| test / T2 / main / C | excess_abstentions | 60 | 0 | [0; 0] |
| test / T2 / main / C | high_confidence_unsupported_points | 42 | 0 | [0; 0] |
| test / T2 / main / D | supported_explanations | 60 | 0.697396 | [0.661979; 0.73125] |
| test / T2 / main / D | source_ids_valid | 60 | 0.9 | [0.8625; 0.9375] |
| test / T2 / main / D | valid_answers | 60 | 0.9 | [0.8625; 0.9375] |
| test / T2 / main / D | brier_sum | 60 | 0.0022626 | [0.000266585; 0.00469514] |
| test / T2 / main / D | correct_abstentions | 60 | 0.893056 | [0.854167; 0.929167] |
| test / T2 / main / D | excess_abstentions | 60 | 0.000320513 | [0; 0.000961538] |
| test / T2 / main / D | high_confidence_unsupported_points | 60 | 0.00694444 | [0; 0.0166667] |

## D. Все 15 сравнений устойчивости

Разность control−main; назначенные отказы сохраняют нули. По 12 миров, T2-линии усреднены.
Интервалы описательные: не отдельные проверки значимости и не доказательство пользы аварии.
| Условие / контроль | Назначений D | Недоступна вторичная модель | Статусы | Разность | 95% CI |
|---|---:|---:|---|---:|---|
| C1 / authentication_ablation | 12 | 0 | {"completed": 11, "skipped_dependency": 1} | -0.0833333 | [-0.25; 0] |
| C1 / crash | 12 | 0 | {"completed": 12} | 0 | [0; 0] |
| C1 / cross_model | 12 | 0 | {"completed": 12} | 0 | [0; 0] |
| C1 / deliberate_false_claim | 12 | 0 | {"completed": 12} | 0 | [0; 0] |
| C1 / forged_source | 12 | 0 | {"completed": 12} | 0 | [0; 0] |
| T1 / authentication_ablation | 12 | 0 | {"completed": 8, "skipped_dependency": 4} | 0.25 | [0; 0.5] |
| T1 / crash | 12 | 0 | {"completed": 7, "skipped_dependency": 5} | 0.166667 | [-0.166667; 0.5] |
| T1 / cross_model | 12 | 0 | {"completed": 5, "skipped_dependency": 7} | 0 | [0; 0] |
| T1 / deliberate_false_claim | 12 | 0 | {"completed": 3, "skipped_dependency": 9} | -0.166667 | [-0.416667; 0.0833333] |
| T1 / forged_source | 12 | 0 | {"completed": 6, "skipped_dependency": 6} | 0.0833333 | [-0.166667; 0.416667] |
| T2 / authentication_ablation | 24 | 0 | {"completed": 23, "skipped_dependency": 1} | 0.125 | [0.0416667; 0.25] |
| T2 / crash | 24 | 0 | {"completed": 23, "skipped_dependency": 1} | 0.125 | [0.0416667; 0.25] |
| T2 / cross_model | 24 | 0 | {"completed": 22, "skipped_dependency": 2} | 0.0833333 | [0; 0.208333] |
| T2 / deliberate_false_claim | 24 | 0 | {"completed": 22, "skipped_dependency": 2} | 0.0833333 | [0; 0.208333] |
| T2 / forged_source | 24 | 0 | {"completed": 22, "skipped_dependency": 2} | 0.0833333 | [-0.0833333; 0.208333] |

## E. Все фиксированные ресурсные сценарии

Ресурс на результат первого условия / второго. У T2 учтены обе линии,все версии,критики и validation.
N — гипотетическое число использований,не наблюдавшиеся повторные deployments.
Неизвестные затраты не заменены нулём. Отдельные стоимости каждого условия сохранены в JSON.
| Контраст | Ресурс | Результат | N=1 | N=10 | N=100 | N=1000 |
|---|---|---|---:|---:|---:|---:|
| T1-C1 | total_tokens | integrative_new | — | — | — | — |
| T1-C1 | total_tokens | identified_new | — | — | — | — |
| T1-C1 | total_tokens | correct_decisions | — | — | — | — |
| T1-C1 | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| T1-C1 | api_plus_mcp_bytes | identified_new | — | — | — | — |
| T1-C1 | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| T1-C1 | context_seconds | integrative_new | 1.51921 | 1.51921 | 1.51921 | 1.51921 |
| T1-C1 | context_seconds | identified_new | 1.51921 | 1.51921 | 1.51921 | 1.51921 |
| T1-C1 | context_seconds | correct_decisions | 1.51025 | 1.51025 | 1.51025 | 1.51025 |
| T2-T1 | total_tokens | integrative_new | — | — | — | — |
| T2-T1 | total_tokens | identified_new | — | — | — | — |
| T2-T1 | total_tokens | correct_decisions | — | — | — | — |
| T2-T1 | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| T2-T1 | api_plus_mcp_bytes | identified_new | — | — | — | — |
| T2-T1 | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| T2-T1 | context_seconds | integrative_new | 49.2589 | 5.51206 | 1.13737 | 0.699906 |
| T2-T1 | context_seconds | identified_new | 49.7574 | 5.56784 | 1.14888 | 0.706989 |
| T2-T1 | context_seconds | correct_decisions | 50.1931 | 5.61659 | 1.15894 | 0.713179 |
| T2-C1 | total_tokens | integrative_new | — | — | — | — |
| T2-C1 | total_tokens | identified_new | — | — | — | — |
| T2-C1 | total_tokens | correct_decisions | — | — | — | — |
| T2-C1 | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| T2-C1 | api_plus_mcp_bytes | identified_new | — | — | — | — |
| T2-C1 | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| T2-C1 | context_seconds | integrative_new | 74.8346 | 8.37397 | 1.72791 | 1.0633 |
| T2-C1 | context_seconds | identified_new | 75.5919 | 8.45872 | 1.7454 | 1.07406 |
| T2-C1 | context_seconds | correct_decisions | 75.8039 | 8.48243 | 1.75029 | 1.07708 |
| C1-FULL-JOURNAL | total_tokens | integrative_new | — | — | — | — |
| C1-FULL-JOURNAL | total_tokens | identified_new | — | — | — | — |
| C1-FULL-JOURNAL | total_tokens | correct_decisions | — | — | — | — |
| C1-FULL-JOURNAL | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| C1-FULL-JOURNAL | api_plus_mcp_bytes | identified_new | — | — | — | — |
| C1-FULL-JOURNAL | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| C1-FULL-JOURNAL | context_seconds | integrative_new | 3.48421 | 3.48421 | 3.48421 | 3.48421 |
| C1-FULL-JOURNAL | context_seconds | identified_new | 3.48926 | 3.48926 | 3.48926 | 3.48926 |
| C1-FULL-JOURNAL | context_seconds | correct_decisions | 3.45775 | 3.45775 | 3.45775 | 3.45775 |
| T1-FULL-JOURNAL | total_tokens | integrative_new | — | — | — | — |
| T1-FULL-JOURNAL | total_tokens | identified_new | — | — | — | — |
| T1-FULL-JOURNAL | total_tokens | correct_decisions | — | — | — | — |
| T1-FULL-JOURNAL | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| T1-FULL-JOURNAL | api_plus_mcp_bytes | identified_new | — | — | — | — |
| T1-FULL-JOURNAL | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| T1-FULL-JOURNAL | context_seconds | integrative_new | 5.29325 | 5.29325 | 5.29325 | 5.29325 |
| T1-FULL-JOURNAL | context_seconds | identified_new | 5.30092 | 5.30092 | 5.30092 | 5.30092 |
| T1-FULL-JOURNAL | context_seconds | correct_decisions | 5.22205 | 5.22205 | 5.22205 | 5.22205 |
| T2-FULL-JOURNAL | total_tokens | integrative_new | — | — | — | — |
| T2-FULL-JOURNAL | total_tokens | identified_new | — | — | — | — |
| T2-FULL-JOURNAL | total_tokens | correct_decisions | — | — | — | — |
| T2-FULL-JOURNAL | api_plus_mcp_bytes | integrative_new | — | — | — | — |
| T2-FULL-JOURNAL | api_plus_mcp_bytes | identified_new | — | — | — | — |
| T2-FULL-JOURNAL | api_plus_mcp_bytes | correct_decisions | — | — | — | — |
| T2-FULL-JOURNAL | context_seconds | integrative_new | 260.74 | 29.1767 | 6.0204 | 3.70478 |
| T2-FULL-JOURNAL | context_seconds | identified_new | 263.76 | 29.5147 | 6.09014 | 3.74769 |
| T2-FULL-JOURNAL | context_seconds | correct_decisions | 262.111 | 29.3301 | 6.05206 | 3.72426 |

Интервалы относятся только к заранее заданным integrative_new,N=100. Любая неопределённая bootstrap-выборка делает CI недоступным.
| Контраст | Ресурс | Отношение при N=100 | 95% CI | Неопределённых / всех выборок |
|---|---|---:|---|---:|
| T1-C1 | total_tokens | — | — | 9853/10000 |
| T1-C1 | api_plus_mcp_bytes | — | — | 8766/10000 |
| T1-C1 | context_seconds | 1.51921 | [1.36448; 1.71817] | 0/10000 |
| T2-T1 | total_tokens | — | — | 10000/10000 |
| T2-T1 | api_plus_mcp_bytes | — | — | 10000/10000 |
| T2-T1 | context_seconds | 1.13737 | [1.00905; 1.26677] | 0/10000 |
| T2-C1 | total_tokens | — | — | 10000/10000 |
| T2-C1 | api_plus_mcp_bytes | — | — | 10000/10000 |
| T2-C1 | context_seconds | 1.72791 | [1.65717; 1.79513] | 0/10000 |
| C1-FULL-JOURNAL | total_tokens | — | — | 9556/10000 |
| C1-FULL-JOURNAL | api_plus_mcp_bytes | — | — | 6363/10000 |
| C1-FULL-JOURNAL | context_seconds | 3.48421 | [3.33876; 3.62824] | 0/10000 |
| T1-FULL-JOURNAL | total_tokens | — | — | 9589/10000 |
| T1-FULL-JOURNAL | api_plus_mcp_bytes | — | — | 9589/10000 |
| T1-FULL-JOURNAL | context_seconds | 5.29325 | [4.76669; 5.98504] | 0/10000 |
| T2-FULL-JOURNAL | total_tokens | — | — | 10000/10000 |
| T2-FULL-JOURNAL | api_plus_mcp_bytes | — | — | 10000/10000 |
| T2-FULL-JOURNAL | context_seconds | 6.0204 | [5.75097; 6.30857] | 0/10000 |

## F. Ограничения чтения таблиц

- Все сравнения ограничены данным конечным корпусом и наблюдавшимися моделями/сервисом.
- В основной метрике учитывается правильный null по совокупности ABC; assigned-information correctness хранится отдельно.
- H2 измеряет наблюдаемые явно связанные пересмотры,не приватные убеждения. Естественные зависимые ошибки здесь не дали наблюдаемых возможностей.
- Пропуски/отказы входят в основные знаменатели; условные Brier и revision rates имеют другие явно указанные знаменатели.
- Никаких дополнительных нескорректированных p для H2/H5/H6 не вычислено.
- Токены и байты с неизвестными попытками неполны; физическое хранение и логические payload/metadata — перекрывающиеся виды,не сумма независимых затрат.
- GPU/CPU модели,энергия,цена,труд автора T1 и полный сетевой overhead не измерены.
