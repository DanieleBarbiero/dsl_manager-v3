## EV_1a4feaf42ef6a00dc9209a39

source_revision_id: REV_1405b7da46624bd98b68aee1
source: vega/plsql/logica_vega.sql
locator: {"char_end":473,"char_start":263,"line_end":16,"line_start":10}

UPDATE ARTICOLO
       SET QTA_DISPONIBILE = QTA_DISPONIBILE - 1
     WHERE ID_ARTICOLO = (
        SELECT ID_ARTICOLO
          FROM RICHIESTA_RICAMBIO
         WHERE ID_RICHIESTA = P_ID_RICHIESTA
     )

## EV_e5f88634cf9dc1d4976c1f6e

source_revision_id: REV_1405b7da46624bd98b68aee1
source: vega/plsql/logica_vega.sql
locator: {"char_end":254,"char_start":155,"line_end":8,"line_start":6}

UPDATE RICHIESTA_RICAMBIO
       SET STATO = 'PRENOTATA'
     WHERE ID_RICHIESTA = P_ID_RICHIESTA
