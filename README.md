# Notiziario

Ogni mattina alle 7:15 (6:15 d'inverno) GitHub scarica le notizie su aerospazio, AI, università e lavoro e attualità, un modello di GitHub Models (gratis) sceglie le più utili e le riassume, la pagina si aggiorna e sul telefono arriva una notifica. Costo zero.

## Pezzi

- `fonti.json`: argomenti, feed, parole chiave e profilo. **È l'unico file da toccare per cambiare cosa leggi.**
- `aggiorna.py`: scarica, filtra, chiede al modello, scrive `docs/giorni/AAAA-MM-GG.json` (tiene 14 giorni).
- `docs/`: la pagina (installabile come app), servita da GitHub Pages.
- `.github/workflows/mattina.yml`: il timer giornaliero.

## Segreti del repository (Settings, Secrets and variables, Actions)

| Nome | Cosa | Obbligatorio |
|---|---|---|
| `NTFY_TOPIC` | nome del canale ntfy, lo stesso a cui sei iscritto nell'app | sì, per la notifica |

Il modello non ha bisogno di chiavi: usa il permesso `models: read` del workflow. Per cambiarlo imposta la variabile `MODELLO` (predefinito `openai/gpt-4.1-mini`).

## Cambiare le fonti

In `fonti.json` ogni fonte è `{"nome": ..., "url": feed RSS}` oppure `{"nome": "Google News", "cerca": "query"}`. La query usa la sintassi di Google News (`OR`, virgolette, `when:1d`). `ore` è quanto indietro guardare, `max` quante notizie mostrare.

Puoi modificarlo direttamente dal sito di GitHub (icona della matita). Dalla mattina dopo vale la nuova versione.

## Lanciarla a mano

Scheda Actions, "Rassegna del mattino", Run workflow. In locale: `python aggiorna.py --senza-notifica`.
