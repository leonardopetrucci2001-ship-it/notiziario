# Notiziario

Ogni mattina alle 7:15 (6:15 d'inverno) GitHub scarica le notizie su aerospazio, AI, università e lavoro e attualità, un modello gratuito di OpenRouter sceglie le più utili e le riassume, la pagina si aggiorna e sul telefono arriva una notifica. Costo zero.

## Pezzi

- `fonti.json`: argomenti, feed, parole chiave e profilo. **È l'unico file da toccare per cambiare cosa leggi.**
- `aggiorna.py`: scarica, filtra, chiede al modello, scrive `docs/giorni/AAAA-MM-GG.json` (tiene 14 giorni).
- `docs/`: la pagina (installabile come app), servita da GitHub Pages.
- `.github/workflows/mattina.yml`: il timer giornaliero.

## Segreti del repository (Settings, Secrets and variables, Actions)

| Nome | Cosa | Obbligatorio |
|---|---|---|
| `NTFY_TOPIC` | nome del canale ntfy, lo stesso a cui sei iscritto nell'app | sì, per la notifica |
| `OPENROUTER_API_KEY` | chiave gratuita da openrouter.ai/keys | no: senza, niente riassunti né "In breve" |

I modelli gratuiti di OpenRouter cambiano spesso. Lo script ne prova tre in ordine (lista `MODELLI` in `aggiorna.py`); se un giorno nessuno risponde, la rassegna esce lo stesso senza riassunti. Limite gratuito: 50 richieste al giorno, ne usiamo 5.

## Cambiare le fonti

In `fonti.json` ogni fonte è `{"nome": ..., "url": feed RSS}` oppure `{"nome": "Google News", "cerca": "query"}`. La query usa la sintassi di Google News (`OR`, virgolette, `when:1d`). `ore` è quanto indietro guardare, `max` quante notizie mostrare.

Puoi modificarlo direttamente dal sito di GitHub (icona della matita). Dalla mattina dopo vale la nuova versione.

## Lanciarla a mano

Scheda Actions, "Rassegna del mattino", Run workflow. In locale: `python aggiorna.py --senza-notifica`.
