# OSA-STRAT-001 — Risk Gate / MISSION 020

**Tryb:** PAPER ONLY; brak deployu, podpisywania, wysyłania transakcji i uruchamiania live tradingu.

## Cel i zachowanie

- Pierwsza strategia korzysta z istniejącego OSA Trading Desk. Nie powstaje drugi bot ani control plane.
- Obowiązkowy CUE Risk Gate w dwóch punktach: przed AI Judge i bezpośrednio w Ledger.buy().
- Domyślnie brak dostawcy świeżych, zweryfikowanych raportów CUE oznacza BLOCK dla wszystkich tokenów.
- Raport M020 z 5 października 2026 stanowi wyłącznie historyczny dowód NO-FORWARD, nie zgodę na BUY.
- Trzy mints z raportu: makemerich, Agency Arcade i $CHIMPSHOT — BLOCK; przy $CHIMPSHOT brak wyjaśnienia 205174 lamportów.
- Wymagane jest siedem kontroli z wynikami PASS, wiązanie dokładnego mint/pair, identyfikator dowodu i świeżość do 90 sekund.
- Typ CueReport sam w sobie nie uwierzytelnia danych. Provider musi niezależnie potwierdzić dane on-chain oraz wykonalność wyjścia; nie jest jeszcze podłączony.
- Dodatnie raporty używane w testach to syntetyczne fixture TEST_ONLY_NOT_ONCHAIN, a nie dowody na żywym rynku.
- Exit istniejących pozycji paper nadal korzysta ze świeżych kwotowań, nie jest blokowany przez brak CUE. Oryginalny globalny HALT wstrzymuje wszystkie paper orders.

## Niezmienione ograniczenia

- Kapitał symulacyjny $1000, limit wejścia 2%, do trzech jednoczesnych pozycji.
- SL -10%, TP +20%, symulowany slippage 0,5% i prowizja 0,25%.
- Zero kluczy prywatnych, zero operacji on-chain, brak publicznego endpointu do wstrzykiwania CUE PASS.
- SHA-256 ledger nadal chroni wewnętrzną spójność logów, a nie stanowi zewnętrznego attestation.

## Akceptacja

cd backend && python -m pytest -q
cd frontend && npm run test:wallet && npm run typecheck && npm run build

Do podłączenia rzeczywistego verifiera konieczny jest osobny audyt i zgoda. W tej wersji brak zaufanego CUE = zero zakupów nawet w paper tradingu.
