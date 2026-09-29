# Acceptance core deterministico

Stato: **passed**.

Baseline: `a7117e061b393123e3b7b2ec22bf171687756447`. HEAD/dirty e hash dello snapshot realmente eseguito sono in `acceptance.json`.

Ambiente: Windows-11-10.0.26200-SP0; Python 3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]; PowerShell 5.1.26100.9444.

| Gate | Esito | Evidenza |
|---|---|---|
| G01 | passed | test_cov_01_missing_fk_retains_declaration, test_cov_02_missing_due_result_is_failure, test_cov_03_ambiguous_and_inconsistent, test_cov_04_composite_counts_and_cov_05_unexpected_resolution, test_cov_07_governance_and_cov_08_unknown_irrelevant |
| G02 | passed | test_biz_01_02_05_06_08_business_cycle, test_other_sql_shapes_ddl_and_quoted_resolver, test_fk_inferred_target_key_order_and_insert_select, test_pinned_v1_ddl_oracle_superset, test_default_null_distinct_from_absent_and_string_literal, test_sqlite_primary_key_does_not_force_not_null |
| G03 | passed | test_biz_03_04_07_decrement_and_names, test_update_typed_literals[NULL-expected0], test_update_typed_literals[''-expected1], test_update_typed_literals[TRUE-expected2], test_update_typed_literals[-123.456789012345678901-expected3], test_update_typed_literals['001'-expected4], test_update_typed_literals[('x')-expected5], test_update_expression_context_and_real_conflicts, test_typed_null_boolean_exact_decimal_full_roundtrip |
| G04 | passed | test_update_expression_context_and_real_conflicts, test_other_sql_shapes_ddl_and_quoted_resolver, test_merge_branches_survive_full_cycle_without_conflict |
| G05 | passed | test_other_sql_shapes_ddl_and_quoted_resolver, test_call_overload_and_dialect_quoting, test_fk_inferred_target_key_order_and_insert_select, test_call_package_body_only_and_spec_precedence, test_resolver_import_order_and_same_named_columns, test_sql_literals_and_unrecognized_preserved, test_oracle_package_members_and_mysql_delimiter, test_cte_alias_not_invented_as_physical_table |
| G06 | passed | test_cov_01_missing_fk_retains_declaration, test_cov_02_missing_due_result_is_failure, test_cov_03_ambiguous_and_inconsistent, test_cov_04_composite_counts_and_cov_05_unexpected_resolution, test_cov_06_dependency_lifecycle_cache_and_history, test_call_overload_and_dialect_quoting, test_resolver_import_order_and_same_named_columns |
| G07 | passed | test_forms_resolution_modes_and_namespace, test_forms_qualified_column_and_inconsistent_table, test_xml_entities_rejected, test_forms_items_keep_block_identity_and_button_operation_can_auto_review |
| G08 | passed | test_chunk_exact_whitespace_fences[], test_chunk_exact_whitespace_fences[ \n\n\t  ], test_chunk_exact_whitespace_fences[# A\n\ntext\n\n### C\nlast], test_chunk_exact_whitespace_fences[# A\n```sql\n# not heading\n```\n## B\nlast], test_chunk_exact_whitespace_fences[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx], test_chunk_exact_whitespace_fences[\r\n# Accenti \xe0 \u6f22\u5b57\r\n\t], test_chunk_configuration_all_paths_and_cache, test_structural_chunker_preserves_text_and_heading_context |
| G09 | passed | test_log_json_identical_occurrences_retry_and_no_conflict, test_log_occurrences |
| G10 | passed | test_format_worker_real[data.csv], test_format_worker_real[data.tsv], test_format_worker_real[data.json], test_format_worker_real[data.jsonl], test_format_worker_real[data.yaml], test_format_worker_real[data.eml], test_format_worker_real[data.mhtml], test_format_worker_real[data.xls], test_format_worker_real[data.ods], test_format_worker_real[data.pptx], test_format_worker_real[data.html], test_format_worker_real[data.sql], test_excel_exact_structural_contract_offline, test_macro_never_executed |
| G11 | passed | test_multi_package_import_review_merge_and_true_conflict, test_biz_01_02_05_06_08_business_cycle, test_deterministic_fact_types_and_relation_epistemics_survive_export, test_diff_tracks_value_correction_as_semantic_change |
| G12 | passed | test_cov_07_governance_and_cov_08_unknown_irrelevant, test_governance_review_merge_idempotence_and_revoke, test_ai_cannot_autoapprove_and_strict_atomic, test_supports_corrections_and_conflicts, test_forms_items_keep_block_identity_and_button_operation_can_auto_review |
| G13 | passed | test_cov_06_dependency_lifecycle_cache_and_history, test_chunk_configuration_all_paths_and_cache, test_rule_only_change_obsoletes_old_outputs_without_review_loss, test_schema2_upgrade_preserves_history, test_dialect_reinterpretation_and_cached_reactivation |
| G14 | passed | test_selection_coverage_explainability_and_budget, test_cov_07_governance_and_cov_08_unknown_irrelevant, test_biz_01_02_05_06_08_business_cycle, test_biz_03_04_07_decrement_and_names, test_biz_04_positive_table_column_constraint_rename, test_partial_ai_remains_visible_and_package_preserves_coverage |
| G15 | passed | test_pinned_v1_ddl_oracle_superset, test_pinned_v1_db_code_forms_and_chunk_oracle, test_excel_exact_structural_contract_offline |
| G16 | passed | vega_deterministic.json |
| G17 | passed | test_windows_bytes_bom_paths_and_locations[utf-8-\n], test_windows_bytes_bom_paths_and_locations[utf-8-\r\n], test_windows_bytes_bom_paths_and_locations[utf-8-sig-\r\n], test_windows_bytes_bom_paths_and_locations[utf-16-\n], test_windows_bytes_bom_paths_and_locations[utf-16-be-\r\n], test_chunk_configuration_all_paths_and_cache, test_schema2_upgrade_preserves_history |
| G18 | passed |  |

| Precisazione | Esito | Atteso verificato | Test |
|---|---|---|---|
| COV-01 | passed | FK declaration retained; missing target blocks exactly the resolved relation | test_cov_01_missing_fk_retains_declaration |
| COV-02 | passed | Complete target resolves; omission of one required output makes the validator fail | test_cov_02_missing_due_result_is_failure |
| COV-03 | passed | Two schema alternatives are ambiguous; mismatched FK arity is inconsistent | test_cov_03_ambiguous_and_inconsistent |
| COV-04 | passed | Derived, missing and blocked components coexist; evidence stays partial | test_cov_04_composite_counts_and_cov_05_unexpected_resolution |
| COV-05 | passed | Internal defects propagate as errors; unexpected unresolved in positive fixture is rejected | test_cov_04_composite_counts_and_cov_05_unexpected_resolution, test_internal_parser_error_is_never_evidence_only |
| COV-06 | passed | Absent/added/modified/removed/restored target invalidates and restores supports without losing review | test_cov_06_dependency_lifecycle_cache_and_history |
| COV-07 | passed | Pending/confirmed/rejected do not change technical coverage; review still gates merge | test_cov_07_governance_and_cov_08_unknown_irrelevant |
| COV-08 | passed | Unknown type fails; unsupported variant explicit; unrelated text does not change candidates | test_cov_07_governance_and_cov_08_unknown_irrelevant |
| BIZ-01 | passed | CHECK IN contains BOZZA, CONFERMATO, ANNULLATO; TOTALE >= exact numeric zero | test_biz_01_02_05_06_08_business_cycle |
| BIZ-02 | passed | NOT NULL is separate from CHECK; removing it changes nullability, precision 12,2 is retained | test_biz_01_02_05_06_08_business_cycle |
| BIZ-03 | passed | QTA_DISPONIBILE - 1 is present; no inventory reservation, units, permissions or domain intentions invented | test_biz_03_04_07_decrement_and_names |
| BIZ-04 | passed | Renamed table, columns and constraints preserve AST operators and literal values under explicit mapping | test_biz_04_positive_table_column_constraint_rename |
| BIZ-05 | passed | SOSPESO and boundary 10 replace prior effective values; history remains and diff is nonempty | test_biz_01_02_05_06_08_business_cycle |
| BIZ-06 | passed | Fresh workspaces; zero AI response imports; only deterministic candidates before explicit test review | test_biz_01_02_05_06_08_business_cycle |
| BIZ-07 | passed | Covered statements excluded from technical route even pending/rejected; partial and domain remain usable | test_cov_07_governance_and_cov_08_unknown_irrelevant, test_biz_03_04_07_decrement_and_names, test_partial_ai_remains_visible_and_package_preserves_coverage |
| BIZ-08 | passed | Literal citations, locators and attributes survive review, merge, reopen and JSON/YAML/Markdown exports | test_biz_01_02_05_06_08_business_cycle |

Tutti i comandi, exit code, tempi, log e versioni sono nel JSON. Il laboratorio integrato usa risposte AI controllate; il laboratorio deterministico e gli audit business non importano AI.

Le regole di business estratte sono solo CHECK, insieme di literal ammessi, limite numerico e nullability dichiarata. Workflow, valuta, autorizzazioni e prenotazioni non sono inferiti dai nomi.

Eccezioni legacy verificate: chunking v1 perde un separatore in un caso; v3 conserva tutto il testo. L'inferenza legacy maps_to → writes_to non è adottata; v3 richiede modalità esplicite.

I contatori applicabili/derivati/mancanti sono sottoinsiemi dei supportati; i candidati e gli oggetti sono conteggi distinti. Un blocco di risoluzione non è una derivazione riuscita. Le fixture negative richiedono espressamente il blocco, quelle positive la risoluzione.

Limiti: subset SQL dichiarato; nessuna esecuzione di SQL/macro o riferimenti esterni. XLSB e backend documentali privi di fixture dedicate restano non certificati. Le prove correnti non attestano piattaforme diverse da quella registrata.
