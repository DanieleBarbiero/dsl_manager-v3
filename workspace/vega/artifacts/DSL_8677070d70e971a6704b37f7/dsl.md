# DSL Manager — conoscenza consolidata

Profilo 2 · 33 fatti · 27 relazioni

## ARTICOLO

- **object_type**: "table"
  - Fonte: vega/database/schema_vega.sql · candidato CAND_776763b7ba2b74b468faadaa · evidenza EV_644b4c4de6cd6a31b9ceabc9

## ARTICOLO.CODICE

- **definition**: {"constraints":["NOT NULL"],"datatype":"VARCHAR2(30)","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_8fdca95a09d0864bc9cba756 · evidenza EV_9864766c352ededda210596d

## ARTICOLO.DESCRIZIONE

- **definition**: {"constraints":["NOT NULL"],"datatype":"VARCHAR2(200)","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_7d76bc119d0fe08fa88a9ade · evidenza EV_57f19f99f0e09eaa7736421c

## ARTICOLO.ID_ARTICOLO

- **definition**: {"constraints":["PRIMARY KEY"],"datatype":"NUMBER","nullable":true}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_f3f5406ccfc7f000c6e62770 · evidenza EV_903887000fc215a2ab4fc453

## ARTICOLO.QTA_DISPONIBILE

- **definition**: {"constraints":["NOT NULL"],"datatype":"NUMBER","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_2421798cfb8a247a41ed4712 · evidenza EV_77d0e87723610dd8ac0eae44

## event:EV_06bc0cc1cabd6127de1482ee

- **occurrence**: {"attributes":{"articolo":"RIC-118","priorita":"P2","richiesta":"RV-1002"},"component":"magazzino","event_kind":"missing","level":"WARNING","message":"missing richiesta=RV-1002 articolo=RIC-118 priorita=P2","occurrence_line":3,"timestamp":"2026-09-01 08:00:02"}
  - Fonte: vega/logs/vega_2026.log · candidato CAND_4ae86ae00a6bc39b478f5650 · evidenza EV_06bc0cc1cabd6127de1482ee

## event:EV_3c9fabdd60da328e93640e3c

- **occurrence**: {"attributes":{"articolo":"RIC-774","quantita":"2","richiesta":"RV-1001"},"component":"scanner","event_kind":"processed","level":"INFO","message":"Processed richiesta=RV-1001 articolo=RIC-774 quantita=2","occurrence_line":2,"timestamp":"2026-09-01 08:00:01"}
  - Fonte: vega/logs/vega_2026.log · candidato CAND_0a71aeaa8bcb76edcd975a3e · evidenza EV_3c9fabdd60da328e93640e3c

## event:EV_7db2a2072a4aadd2d37305ef

- **occurrence**: {"attributes":{"priorita":"P1","richiesta":"RV-1001"},"component":"scanner","event_kind":"start","level":"INFO","message":"Start richiesta=RV-1001 priorita=P1","occurrence_line":1,"timestamp":"2026-09-01 08:00:00"}
  - Fonte: vega/logs/vega_2026.log · candidato CAND_a6b90c649801a2a4433d75e0 · evidenza EV_7db2a2072a4aadd2d37305ef

## event:EV_a3e973b29852e1ff80cbef12

- **occurrence**: {"attributes":{"esito":"inoltrata","richiesta":"RV-1001"},"component":"scanner","event_kind":"end","level":"INFO","message":"End richiesta=RV-1001 esito=inoltrata","occurrence_line":5,"timestamp":"2026-09-01 08:00:04"}
  - Fonte: vega/logs/vega_2026.log · candidato CAND_969b0d7288e0dc5d3c3f6d65 · evidenza EV_a3e973b29852e1ff80cbef12

## event:EV_d770f3a7d8f01853e8acfcfb

- **occurrence**: {"attributes":{"articolo":"RIC-118","disponibilita":"parziale","richiesta":"RV-1002"},"component":"magazzino","event_kind":"processed","level":"INFO","message":"Processed richiesta=RV-1002 articolo=RIC-118 disponibilita=parziale","occurrence_line":4,"timestamp":"2026-09-01 08:00:03"}
  - Fonte: vega/logs/vega_2026.log · candidato CAND_31914dfda446e146ad465e00 · evidenza EV_d770f3a7d8f01853e8acfcfb

## FRM_RICHIESTA

- **definition**: {"object_type":"form","title":"Richiesta ricambio"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_b056bdcf939685d2c1a485b1 · evidenza EV_011507284cbc8e6474a7b870

## FRM_RICHIESTA.BTN_PRENOTA

- **definition**: {"column":"BTN_PRENOTA","datatype":null,"form":"FRM_RICHIESTA","label":"Prenota","object_type":"button","required":false,"table":null}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_291ec4ffc0c3e1c33a9e8b59 · evidenza EV_8a1d4d5156822ebe363722c2

## FRM_RICHIESTA.ID_ARTICOLO

- **definition**: {"column":"ID_ARTICOLO","datatype":"NUMBER","form":"FRM_RICHIESTA","label":null,"object_type":"field","required":true,"table":"RICHIESTA_RICAMBIO"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_627df2dcad4a91992e2d8ce3 · evidenza EV_e63aa75ffbb8846e680f8381

## FRM_RICHIESTA.ID_RICHIESTA

- **definition**: {"column":"ID_RICHIESTA","datatype":"NUMBER","form":"FRM_RICHIESTA","label":null,"object_type":"field","required":true,"table":"RICHIESTA_RICAMBIO"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_1a3cea0eae9ece5fab5329ed · evidenza EV_1bfa40e755916fe8d926952b

## FRM_RICHIESTA.PRIORITA

- **definition**: {"column":"PRIORITA","datatype":"VARCHAR2","form":"FRM_RICHIESTA","label":null,"object_type":"field","required":true,"table":"RICHIESTA_RICAMBIO"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_058d375839edd0e5688e90f1 · evidenza EV_4affc4e2688893d9829e0110

## FRM_RICHIESTA.RICHIESTA_RICAMBIO

- **definition**: {"object_type":"block","table":"RICHIESTA_RICAMBIO"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_019df486f1f90f291bf4103c · evidenza EV_7207c3bab9b6abe3eef239df

## FRM_RICHIESTA.STATO

- **definition**: {"column":"STATO","datatype":"VARCHAR2","form":"FRM_RICHIESTA","label":null,"object_type":"field","required":true,"table":"RICHIESTA_RICAMBIO"}
  - Fonte: vega/forms/frm_richiesta.xml · candidato CAND_7908c19e1e4bde95eefc2790 · evidenza EV_36058b6a427add9f34718a8e

## magazzino


## matrice_priorita_vega_2026.xlsx

- **definition**: {"object_type":"excel_workbook"}
  - Fonte: vega/documenti/matrice_priorita_vega_2026.xlsx · candidato CAND_6feba0e81be5235a76cb649c · evidenza EV_3e495a10e162932326caba67

## matrice_priorita_vega_2026.xlsx::Priorita

- **definition**: {"dimensions":{"declared":null,"max_column":4,"max_row":5,"min_column":1,"min_row":1},"object_type":"excel_sheet","sheet_name":"Priorita","visibility":"visible"}
  - Fonte: vega/documenti/matrice_priorita_vega_2026.xlsx · candidato CAND_b11163c09f69822b2ff93b31 · evidenza EV_8fe04ffa1659213c5de24684

## matrice_priorita_vega_2026.xlsx::Priorita::A1:D5

- **definition**: {"detector":{"id":"connected_non_empty_cells","version":"1"},"end_cell":"D5","fragment_hash":"6471cb5fe36d722903ec7a908204528e9bad36ba3533a32428302a32c7d640ec","fragment_type":"excel_region","object_type":"excel_region","region_hash":"20aada49828c65a87d0bf8b42c319b780ed4b87f57b299507572f9797efcf4fe","region_kind":"connected_cells","sequence":1,"sheet":{"index":0,"name":"Priorita"},"start_cell":"A1"}
  - Fonte: vega/documenti/matrice_priorita_vega_2026.xlsx · candidato CAND_106ee36d77b34465f38859b9 · evidenza EV_af0833b4e7a1854a095b01ce

## PRC_PRENOTA_ARTICOLO

- **object_type**: "procedure"
  - Fonte: vega/plsql/logica_vega.sql · candidato CAND_50302c23b0d01a0ab56d4902 · evidenza EV_e66cb31f395ded6fc2dcb0b6

## Prenotazione articolo

- **effetto_su_disponibilita**: "riduzione"
  - Fonte: vega/documenti/manuale_operativo_vega_2026.docx · candidato CAND_c9afcc3fd44d554dd0a556b7 · evidenza EV_9a6d6ccaa86083d021452d9a

## RAISE_APPLICATION_ERROR


## Regole correnti

- **decorrenza**: "2026-09-01"
  - Fonte: vega/documenti/manuale_operativo_vega_2026.docx · candidato CAND_122c4d232bbeca5a0661d29e · evidenza EV_9a6d6ccaa86083d021452d9a

## Richiesta P1

- **tempo_presa_in_carico**: "30 minuti"
  - Fonte: vega/documenti/manuale_operativo_vega_2026.docx · candidato CAND_139717f9a690cf6a74bd3e45 · evidenza EV_9a6d6ccaa86083d021452d9a

## Richiesta ricambio

- **prerequisito_chiusura**: "CONSEGNATA"
  - Fonte: vega/documenti/manuale_operativo_vega_2026.docx · candidato CAND_4642bdc3bb7b9de55844673d · evidenza EV_9a6d6ccaa86083d021452d9a

## RICHIESTA_RICAMBIO

- **object_type**: "table"
  - Fonte: vega/database/schema_vega.sql · candidato CAND_8d3e788bda22312db144fe9f · evidenza EV_e1ebf3e49a1722713b83c531

## RICHIESTA_RICAMBIO.ID_ARTICOLO

- **definition**: {"constraints":["NOT NULL"],"datatype":"NUMBER","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_cc2d6733887842a6517e8580 · evidenza EV_f9891db7fafc3b02db607705

## RICHIESTA_RICAMBIO.ID_RICHIESTA

- **definition**: {"constraints":["PRIMARY KEY"],"datatype":"NUMBER","nullable":true}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_ff4e0051b00f297118cb1f60 · evidenza EV_cf2604e6e0ba5b6a0680b839

## RICHIESTA_RICAMBIO.PRIORITA

- **definition**: {"constraints":["NOT NULL"],"datatype":"VARCHAR2(10)","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_253c87ce16a71fcdeba6cfed · evidenza EV_c24188bc38c875f41caebf2e

## RICHIESTA_RICAMBIO.QTA_RICHIESTA

- **definition**: {"constraints":["NOT NULL"],"datatype":"NUMBER","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_33568bf54eacca82b7e5a876 · evidenza EV_81feb777cd7c681ca84a17c2

## RICHIESTA_RICAMBIO.STATO

- **definition**: {"constraints":["NOT NULL"],"datatype":"VARCHAR2(20)","nullable":false}
  - Fonte: vega/database/schema_vega.sql · candidato CAND_a0d9cb57786fc079de6575e3 · evidenza EV_18cdfce597666e265d1f7d87

## RV-1002

- **magazzino**: "missing articolo=RIC-118 priorita=P2"
  - Fonte: vega/logs/vega_2026.log · candidato CAND_db85cf23fb16e12fb2356179 · evidenza EV_06bc0cc1cabd6127de1482ee

## scanner


## TRG_CHIUDI_RICHIESTA

- **object_type**: "trigger"
  - Fonte: vega/plsql/logica_vega.sql · candidato CAND_a024191d4860c3a02de140af · evidenza EV_f73e3125e76e0cf1e9b509ae

## Relazioni

- event:EV_7db2a2072a4aadd2d37305ef → observed_on → scanner
- PRC_PRENOTA_ARTICOLO → updates_status_to_PRENOTATA → RICHIESTA_RICAMBIO
- PRC_PRENOTA_ARTICOLO → writes_to → ARTICOLO.QTA_DISPONIBILE
- PRC_PRENOTA_ARTICOLO → reads_from → ARTICOLO.ID_ARTICOLO
- FRM_RICHIESTA.PRIORITA → maps_to → RICHIESTA_RICAMBIO.PRIORITA
- PRC_PRENOTA_ARTICOLO → reads_from → RICHIESTA_RICAMBIO.ID_ARTICOLO
- event:EV_06bc0cc1cabd6127de1482ee → observed_on → magazzino
- FRM_RICHIESTA → uses_table → RICHIESTA_RICAMBIO
- TRG_CHIUDI_RICHIESTA → calls → RAISE_APPLICATION_ERROR
- PRC_PRENOTA_ARTICOLO → reads_from → RICHIESTA_RICAMBIO.ID_RICHIESTA
- PRC_PRENOTA_ARTICOLO → writes_to → RICHIESTA_RICAMBIO
- TRG_CHIUDI_RICHIESTA → reads_from → RICHIESTA_RICAMBIO.STATO
- PRC_PRENOTA_ARTICOLO → reads_from → ARTICOLO.QTA_DISPONIBILE
- PRC_PRENOTA_ARTICOLO → decrements_available_quantity → ARTICOLO.QTA_DISPONIBILE
- event:EV_3c9fabdd60da328e93640e3c → observed_on → scanner
- RICHIESTA_RICAMBIO.ID_ARTICOLO → foreign_key_reference → ARTICOLO.ID_ARTICOLO
- event:EV_d770f3a7d8f01853e8acfcfb → observed_on → magazzino
- FRM_RICHIESTA.STATO → maps_to → RICHIESTA_RICAMBIO.STATO
- FRM_RICHIESTA.ID_ARTICOLO → maps_to → RICHIESTA_RICAMBIO.ID_ARTICOLO
- event:EV_a3e973b29852e1ff80cbef12 → observed_on → scanner
- FRM_RICHIESTA.BTN_PRENOTA → calls → PRC_PRENOTA_ARTICOLO
- TRG_CHIUDI_RICHIESTA → trigger_on → RICHIESTA_RICAMBIO
- PRC_PRENOTA_ARTICOLO → reads_from → RICHIESTA_RICAMBIO
- RICHIESTA_RICAMBIO → foreign_key → ARTICOLO
- FRM_RICHIESTA.ID_RICHIESTA → maps_to → RICHIESTA_RICAMBIO.ID_RICHIESTA
- PRC_PRENOTA_ARTICOLO → writes_to → RICHIESTA_RICAMBIO.STATO
- PRC_PRENOTA_ARTICOLO → writes_to → ARTICOLO

## Conflitti

