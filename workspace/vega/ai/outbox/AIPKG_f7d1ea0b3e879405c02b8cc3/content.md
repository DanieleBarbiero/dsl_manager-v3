## EV_b0ee39146fdb10e756fc9a44

source_revision_id: REV_c541599e315757cabfedd178
source: vega/plsql/logica_vega.sql
locator: {"char_end":247,"char_start":150,"line_end":8,"line_start":6}

UPDATE RICHIESTA_RICAMBIO
       SET STATO = 'PRENOTATA'
     WHERE ID_RICHIESTA = P_ID_RICHIESTA

## EV_faa58f5a85eaf9c190ae5f7b

source_revision_id: REV_c541599e315757cabfedd178
source: vega/plsql/logica_vega.sql
locator: {"char_end":458,"char_start":254,"line_end":16,"line_start":10}

UPDATE ARTICOLO
       SET QTA_DISPONIBILE = QTA_DISPONIBILE - 1
     WHERE ID_ARTICOLO = (
        SELECT ID_ARTICOLO
          FROM RICHIESTA_RICAMBIO
         WHERE ID_RICHIESTA = P_ID_RICHIESTA
     )
