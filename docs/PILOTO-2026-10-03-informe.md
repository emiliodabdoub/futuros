# Informe del piloto — experimento A (LR-v1 sin Jev)

Manifiesto `pilot-orderflow-v1` · job `GLBX-20261003-8EMSSXN9Y7` · ventana 2024-09-05T00:00:00Z → 2024-09-21T00:00:00Z · esquema mbp-10 · días degradados: None

Resultado de ingeniería sobre 10 sesiones. **No es evidencia de ventaja estadística** (protocolo §1).

## 1. Datos por sesión y contrato (ventana 08:00–12:00 NY)

| Sesión | Contrato | Registros | Trades | Volumen | Agresor conocido % | Resets | Fuera de rejilla | Saltos seq | Epochs bloqueados | Motivos de bloqueo | Barras 1m | Revisiones tardías | s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 2024-09-09 | ESU4 | 14,750,000 | 180,680 | 623,759 | 100.0 | 0 | 0 | 670,054 | 4800/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 300} | 239 | 0 | 195.0 |
| 2024-09-09 | GCZ4 | 24,170,236 | 23,980 | 44,163 | 98.764 | 0 | 0 | 308,710 | 4837/14399 | {'REGIME_UNKNOWN': 4500, 'STALE_FEED': 5, 'AGGRESSOR_UNKNOWN_HIGH': 564} | 239 | 0 | 59.9 |
| 2024-09-09 | NQU4 | 14,750,000 | 155,279 | 223,569 | 100.0 | 0 | 0 | 3,001,551 | 4860/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 360} | 239 | 0 | 206.4 |
| 2024-09-10 | ESU4 | 16,500,000 | 198,347 | 621,614 | 100.0 | 0 | 0 | 919,452 | 5100/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 600} | 239 | 0 | 224.3 |
| 2024-09-10 | GCZ4 | 26,179,427 | 33,350 | 61,055 | 98.934 | 0 | 0 | 400,384 | 4997/14399 | {'REGIME_UNKNOWN': 4500, 'STALE_FEED': 10, 'AGGRESSOR_UNKNOWN_HIGH': 508, 'VOL_SHOCK': 600} | 239 | 0 | 66.8 |
| 2024-09-10 | NQU4 | 16,500,000 | 175,937 | 245,063 | 100.0 | 0 | 0 | 3,434,275 | 4860/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 360} | 239 | 0 | 240.6 |
| 2024-09-11 | ESU4 | 21,000,000 | 297,329 | 984,867 | 100.0 | 0 | 0 | 1,397,074 | 4979/14399 | {'REGIME_UNKNOWN': 4500, 'MACRO_BLOCK:CPI': 900, 'VOL_SHOCK': 839} | 239 | 0 | 325.7 |
| 2024-09-11 | GCZ4 | 35,362,893 | 49,403 | 88,519 | 99.117 | 0 | 0 | 714,529 | 4522/14399 | {'REGIME_UNKNOWN': 4500, 'STALE_FEED': 4, 'AGGRESSOR_UNKNOWN_HIGH': 93, 'MACRO_BLOCK:CPI': 900, 'VOL_SHOCK': 360} | 239 | 0 | 108.2 |
| 2024-09-11 | NQU4 | 21,000,000 | 228,361 | 328,627 | 100.0 | 0 | 0 | 4,562,059 | 4860/14399 | {'REGIME_UNKNOWN': 4500, 'MACRO_BLOCK:CPI': 900, 'VOL_SHOCK': 720} | 239 | 0 | 350.9 |
| 2024-09-12 | ESU4 | 21,750,000 | 239,412 | 693,230 | 100.0 | 0 | 0 | 1,589,575 | 5400/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 1200} | 239 | 0 | 344.1 |
| 2024-09-12 | GCZ4 | 21,750,000 | 65,818 | 125,008 | 98.754 | 0 | 0 | 758,810 | 5012/14399 | {'REGIME_UNKNOWN': 4500, 'STALE_FEED': 3, 'AGGRESSOR_UNKNOWN_HIGH': 578, 'VOL_SHOCK': 600} | 239 | 0 | 91.2 |
| 2024-09-12 | NQU4 | 21,750,000 | 200,444 | 278,562 | 100.0 | 0 | 0 | 4,425,579 | 5580/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 1380} | 239 | 0 | 333.1 |
| 2024-09-13 | ESZ4 | 19,250,000 | 61,529 | 115,590 | 99.952 | 0 | 0 | 1,238,423 | 5117/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 600, 'CROSSED_BOOK_PERSISTENT': 4, 'AGGRESSOR_UNKNOWN_HIGH': 13} | 239 | 0 | 160.9 |
| 2024-09-13 | GCZ4 | 31,808,674 | 33,405 | 61,455 | 98.4 | 0 | 0 | 458,605 | 5354/14399 | {'REGIME_UNKNOWN': 4500, 'AGGRESSOR_UNKNOWN_HIGH': 974, 'STALE_FEED': 3} | 239 | 0 | 88.3 |
| 2024-09-13 | NQZ4 | 19,250,000 | 28,048 | 34,823 | 100.0 | 0 | 0 | 2,451,584 | 5220/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 720} | 239 | 0 | 190.1 |
| 2024-09-16 | ESZ4 | 29,825,797 | 116,668 | 299,695 | 100.0 | 0 | 0 | 1,384,223 | 4980/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 480} | 239 | 0 | 234.3 |
| 2024-09-16 | GCZ4 | 29,825,797 | 25,475 | 45,557 | 98.887 | 0 | 0 | 357,692 | 5527/14399 | {'REGIME_UNKNOWN': 4500, 'AGGRESSOR_UNKNOWN_HIGH': 435, 'STALE_FEED': 12, 'VOL_SHOCK': 600} | 239 | 0 | 78.3 |
| 2024-09-16 | NQZ4 | 29,825,797 | 100,371 | 134,055 | 100.0 | 0 | 0 | 3,234,994 | 4980/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 480} | 239 | 0 | 266.9 |
| 2024-09-17 | ESZ4 | 22,250,000 | 155,782 | 445,605 | 100.0 | 0 | 0 | 1,527,745 | 4800/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 600} | 239 | 0 | 268.5 |
| 2024-09-17 | GCZ4 | 22,250,000 | 33,535 | 60,566 | 98.458 | 0 | 0 | 478,345 | 4990/14399 | {'REGIME_UNKNOWN': 4500, 'AGGRESSOR_UNKNOWN_HIGH': 631, 'VOL_SHOCK': 660, 'STALE_FEED': 1} | 239 | 0 | 72.7 |
| 2024-09-17 | NQZ4 | 40,857,334 | 133,501 | 182,912 | 100.0 | 0 | 0 | 3,779,793 | 4980/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 780} | 239 | 0 | 322.0 |
| 2024-09-18 | ESZ4 | 14,250,000 | 109,951 | 350,879 | 100.0 | 0 | 0 | 937,508 | 5460/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 960} | 239 | 0 | 162.4 |
| 2024-09-18 | GCZ4 | 34,741,564 | 18,858 | 33,078 | 98.851 | 0 | 0 | 270,949 | 5395/14399 | {'REGIME_UNKNOWN': 4500, 'STALE_FEED': 4, 'AGGRESSOR_UNKNOWN_HIGH': 862, 'VOL_SHOCK': 300} | 239 | 0 | 82.3 |
| 2024-09-18 | NQZ4 | 34,741,564 | 100,600 | 139,440 | 100.0 | 0 | 0 | 2,463,656 | 4800/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 300} | 239 | 0 | 226.8 |
| 2024-09-19 | ESZ4 | 22,500,000 | 206,750 | 649,550 | 100.0 | 0 | 0 | 1,303,279 | 4800/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 600} | 239 | 0 | 243.9 |
| 2024-09-19 | GCZ4 | 33,936,304 | 39,532 | 72,307 | 98.996 | 0 | 0 | 548,969 | 4857/14399 | {'REGIME_UNKNOWN': 4500, 'AGGRESSOR_UNKNOWN_HIGH': 552, 'VOL_SHOCK': 300} | 239 | 0 | 101.4 |
| 2024-09-19 | NQZ4 | 22,500,000 | 170,908 | 239,197 | 100.0 | 0 | 0 | 3,223,630 | 5100/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 1200} | 239 | 0 | 253.6 |
| 2024-09-20 | ESZ4 | 13,000,000 | 202,918 | 664,262 | 100.0 | 0 | 0 | 457,461 | 4500/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 300} | 239 | 0 | 228.2 |
| 2024-09-20 | GCZ4 | 20,040,158 | 45,432 | 83,375 | 98.667 | 0 | 0 | 602,974 | 5387/14399 | {'REGIME_UNKNOWN': 4500, 'AGGRESSOR_UNKNOWN_HIGH': 769, 'VOL_SHOCK': 300} | 239 | 0 | 80.2 |
| 2024-09-20 | NQZ4 | 13,000,000 | 159,143 | 227,512 | 100.0 | 0 | 0 | 2,600,446 | 4920/14399 | {'REGIME_UNKNOWN': 4500, 'VOL_SHOCK': 720} | 239 | 0 | 190.6 |

## 2. Selección causal de contrato y niveles del día anterior

| Sesión/root | Contrato | Volumen sesión previa | Fecha volumen | Prior high (ticks) | Prior low (ticks) |
|---|---|---:|---|---:|---:|
| 2024-09-09/ES | ESU4 | 2,249,124 | 2024-09-06 | 22130 | 21641 |
| 2024-09-09/GC | GCZ4 | 214,469 | 2024-09-06 | 25484 | 25139 |
| 2024-09-09/NQ | NQU4 | 705,865 | 2024-09-06 | 75869 | 73721 |
| 2024-09-10/ES | ESU4 | 1,503,643 | 2024-09-09 | 21972 | 21770 |
| 2024-09-10/GC | GCZ4 | 131,839 | 2024-09-09 | 25358 | 25222 |
| 2024-09-10/NQ | NQU4 | 518,312 | 2024-09-09 | 74920 | 73989 |
| 2024-09-11/ES | ESU4 | 1,450,341 | 2024-09-10 | 22024 | 21793 |
| 2024-09-11/GC | GCZ4 | 146,583 | 2024-09-10 | 25475 | 25297 |
| 2024-09-11/NQ | NQU4 | 526,896 | 2024-09-10 | 75514 | 74359 |
| 2024-09-12/ES | ESU4 | 2,147,191 | 2024-09-11 | 22270 | 21648 |
| 2024-09-12/GC | GCZ4 | 185,078 | 2024-09-11 | 25490 | 25290 |
| 2024-09-12/NQ | NQU4 | 709,416 | 2024-09-11 | 77174 | 74188 |
| 2024-09-13/ES | ESZ4 | 115,147 | 2024-09-12 | 22668 | 22401 |
| 2024-09-13/GC | GCZ4 | 217,562 | 2024-09-12 | 25877 | 25658 |
| 2024-09-13/NQ | NQZ4 | 17,475 | 2024-09-12 | 78867 | 77673 |
| 2024-09-16/ES | ESZ4 | 291,354 | 2024-09-13 | 22809 | 22661 |
| 2024-09-16/GC | GCZ4 | 152,274 | 2024-09-13 | 26146 | 26012 |
| 2024-09-16/NQ | NQZ4 | 81,385 | 2024-09-13 | 79254 | 78539 |
| 2024-09-17/ES | ESZ4 | 646,179 | 2024-09-16 | 22811 | 22678 |
| 2024-09-17/GC | GCZ4 | 112,604 | 2024-09-16 | 26168 | 26037 |
| 2024-09-17/NQ | NQZ4 | 267,358 | 2024-09-16 | 78790 | 78116 |
| 2024-09-18/ES | ESZ4 | 1,115,425 | 2024-09-17 | 22948 | 22711 |
| 2024-09-18/GC | GCZ4 | 149,546 | 2024-09-17 | 26095 | 25873 |
| 2024-09-18/NQ | NQZ4 | 409,505 | 2024-09-17 | 79401 | 78298 |
| 2024-09-19/ES | ESZ4 | 1,456,512 | 2024-09-18 | 23023 | 22701 |
| 2024-09-19/GC | GCZ4 | 220,819 | 2024-09-18 | 26272 | 25725 |
| 2024-09-19/NQ | NQZ4 | 515,418 | 2024-09-18 | 79600 | 78232 |
| 2024-09-20/ES | ESZ4 | 1,492,597 | 2024-09-19 | 23190 | 22993 |
| 2024-09-20/GC | GCZ4 | 189,067 | 2024-09-19 | 26182 | 25943 |
| 2024-09-20/NQ | NQZ4 | 559,298 | 2024-09-19 | 80812 | 79856 |

## 3. Agregados diarios (sesión completa, todos los instrumentos del archivo)

| Fecha | Registros | Instrumento | Volumen | Trades | Agresor conocido % | RTH high | RTH low | RTH vol |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| 2024-09-05 | 27,917,698 | 106364 | 3,946 | 3,192 | 100.0 | 19376250000000 | 19077000000000 | 2,628 |
| 2024-09-05 | 27,917,698 | 118 | 1,666,149 | 502,047 | 99.998 | 5557250000000 | 5490000000000 | 1,361,344 |
| 2024-09-05 | 27,917,698 | 183748 | 18,208 | 13,418 | 100.0 | 5616500000000 | 5548500000000 | 11,434 |
| 2024-09-05 | 27,917,698 | 393 | 144,109 | 81,847 | 98.408 | 2550900000000 | 2533700000000 | 59,217 |
| 2024-09-05 | 27,917,698 | 4358 | 574,465 | 402,215 | 99.999 | 19150500000000 | 18842000000000 | 436,984 |
| 2024-09-06 | 36,214,555 | 106364 | 6,153 | 5,108 | 100.0 | 19191250000000 | 18651500000000 | 3,937 |
| 2024-09-06 | 36,214,555 | 118 | 2,249,124 | 687,287 | 99.993 | 5532500000000 | 5410250000000 | 1,774,209 |
| 2024-09-06 | 36,214,555 | 183748 | 40,488 | 29,083 | 99.993 | 5590500000000 | 5467750000000 | 27,200 |
| 2024-09-06 | 36,214,555 | 393 | 214,469 | 119,385 | 98.839 | 2548400000000 | 2513900000000 | 128,241 |
| 2024-09-06 | 36,214,555 | 4358 | 705,865 | 490,801 | 100.0 | 18967250000000 | 18430250000000 | 535,106 |
| 2024-09-08 | 681,188 | 106364 | 236 | 170 | 84.322 | None | None | 0 |
| 2024-09-08 | 681,188 | 118 | 27,034 | 10,991 | 99.515 | None | None | 0 |
| 2024-09-08 | 681,188 | 183748 | 429 | 251 | 99.767 | None | None | 0 |
| 2024-09-08 | 681,188 | 393 | 4,839 | 2,386 | 99.256 | None | None | 0 |
| 2024-09-08 | 681,188 | 4358 | 13,206 | 9,869 | 99.697 | None | None | 0 |
| 2024-09-09 | 24,170,236 | 106364 | 4,679 | 3,945 | 100.0 | 18953250000000 | 18719000000000 | 3,120 |
| 2024-09-09 | 24,170,236 | 118 | 1,503,643 | 420,230 | 99.998 | 5493000000000 | 5442500000000 | 1,205,943 |
| 2024-09-09 | 24,170,236 | 183748 | 23,255 | 16,486 | 99.991 | 5552000000000 | 5500250000000 | 16,022 |
| 2024-09-09 | 24,170,236 | 393 | 131,839 | 71,778 | 98.736 | 2535800000000 | 2522200000000 | 48,221 |
| 2024-09-09 | 24,170,236 | 4358 | 518,312 | 356,465 | 99.998 | 18730000000000 | 18497250000000 | 401,148 |
| 2024-09-10 | 26,179,427 | 106364 | 5,174 | 4,247 | 100.0 | 19101750000000 | 18815000000000 | 3,868 |
| 2024-09-10 | 26,179,427 | 118 | 1,450,341 | 437,660 | 99.999 | 5506000000000 | 5448250000000 | 1,189,802 |
| 2024-09-10 | 26,179,427 | 183748 | 30,183 | 21,351 | 100.0 | 5564500000000 | 5506500000000 | 21,473 |
| 2024-09-10 | 26,179,427 | 393 | 146,583 | 75,667 | 99.161 | 2547500000000 | 2529700000000 | 71,497 |
| 2024-09-10 | 26,179,427 | 4358 | 526,896 | 367,414 | 99.999 | 18878500000000 | 18589750000000 | 412,590 |
| 2024-09-11 | 35,362,893 | 106364 | 11,652 | 8,843 | 100.0 | 19523500000000 | 18773500000000 | 9,014 |
| 2024-09-11 | 35,362,893 | 118 | 2,147,191 | 620,534 | 99.999 | 5567500000000 | 5412000000000 | 1,778,466 |
| 2024-09-11 | 35,362,893 | 183748 | 57,986 | 38,602 | 99.993 | 5627000000000 | 5470000000000 | 43,630 |
| 2024-09-11 | 35,362,893 | 393 | 185,078 | 98,981 | 99.059 | 2549000000000 | 2529000000000 | 70,168 |
| 2024-09-11 | 35,362,893 | 4358 | 709,416 | 486,543 | 99.999 | 19293500000000 | 18547000000000 | 558,727 |
| 2024-09-12 | 33,194,304 | 106364 | 17,475 | 13,806 | 99.828 | 19716750000000 | 19418250000000 | 10,163 |
| 2024-09-12 | 33,194,304 | 118 | 1,516,992 | 481,902 | 99.998 | 5607000000000 | 5540250000000 | 1,233,410 |
| 2024-09-12 | 33,194,304 | 183748 | 115,147 | 68,080 | 99.997 | 5667000000000 | 5600250000000 | 86,557 |
| 2024-09-12 | 33,194,304 | 393 | 217,562 | 114,389 | 98.729 | 2587700000000 | 2565800000000 | 101,598 |
| 2024-09-12 | 33,194,304 | 4358 | 563,427 | 398,933 | 99.997 | 19483500000000 | 19185000000000 | 431,086 |
| 2024-09-13 | 31,808,674 | 106364 | 81,385 | 64,934 | 100.0 | 19813500000000 | 19634750000000 | 61,161 |
| 2024-09-13 | 31,808,674 | 118 | 1,033,964 | 318,350 | 99.979 | 5641500000000 | 5605000000000 | 865,156 |
| 2024-09-13 | 31,808,674 | 183748 | 291,354 | 141,371 | 99.981 | 5702250000000 | 5665250000000 | 242,114 |
| 2024-09-13 | 31,808,674 | 393 | 152,274 | 84,364 | 98.318 | 2614600000000 | 2601200000000 | 67,993 |
| 2024-09-13 | 31,808,674 | 4358 | 412,359 | 287,935 | 100.0 | 19577250000000 | 19398250000000 | 339,551 |
| 2024-09-15 | 588,471 | 106364 | 3,909 | 3,039 | 99.949 | None | None | 0 |
| 2024-09-15 | 588,471 | 118 | 9,902 | 4,183 | 99.02 | None | None | 0 |
| 2024-09-15 | 588,471 | 183748 | 5,289 | 3,044 | 99.565 | None | None | 0 |
| 2024-09-15 | 588,471 | 393 | 4,808 | 2,829 | 98.482 | None | None | 0 |
| 2024-09-15 | 588,471 | 4358 | 6,473 | 4,802 | 99.66 | None | None | 0 |
| 2024-09-16 | 29,825,797 | 106364 | 267,358 | 198,072 | 99.999 | 19697500000000 | 19529000000000 | 214,076 |
| 2024-09-16 | 29,825,797 | 118 | 454,587 | 170,206 | 100.0 | 5641500000000 | 5609250000000 | 365,541 |
| 2024-09-16 | 29,825,797 | 183748 | 646,179 | 228,392 | 100.0 | 5702750000000 | 5669500000000 | 552,300 |
| 2024-09-16 | 29,825,797 | 393 | 112,604 | 63,095 | 98.592 | 2616800000000 | 2603700000000 | 45,116 |
| 2024-09-16 | 29,825,797 | 4358 | 222,990 | 156,207 | 99.997 | 19463500000000 | 19299250000000 | 177,114 |
| 2024-09-17 | 40,857,334 | 106364 | 409,505 | 295,121 | 100.0 | 19850250000000 | 19574500000000 | 331,662 |
| 2024-09-17 | 40,857,334 | 118 | 391,229 | 185,808 | 99.999 | 5675500000000 | 5617000000000 | 317,973 |
| 2024-09-17 | 40,857,334 | 183748 | 1,115,425 | 384,210 | 99.999 | 5737000000000 | 5677750000000 | 956,897 |
| 2024-09-17 | 40,857,334 | 393 | 149,546 | 80,923 | 98.746 | 2609500000000 | 2587300000000 | 62,709 |
| 2024-09-17 | 40,857,334 | 4358 | 145,557 | 107,511 | 99.998 | 19615500000000 | 19341000000000 | 111,994 |
| 2024-09-18 | 34,741,564 | 106364 | 515,418 | 374,076 | 99.997 | 19900000000000 | 19558000000000 | 429,079 |
| 2024-09-18 | 34,741,564 | 118 | 294,338 | 150,298 | 99.961 | 5696250000000 | 5613750000000 | 250,087 |
| 2024-09-18 | 34,741,564 | 183748 | 1,456,512 | 579,495 | 99.97 | 5755750000000 | 5675250000000 | 1,279,597 |
| 2024-09-18 | 34,741,564 | 393 | 220,819 | 120,940 | 98.601 | 2627200000000 | 2572500000000 | 150,984 |
| 2024-09-18 | 34,741,564 | 4358 | 84,536 | 63,599 | 99.999 | 19660000000000 | 19331000000000 | 62,627 |
| 2024-09-19 | 33,936,304 | 106364 | 559,298 | 396,914 | 99.999 | 20203000000000 | 19964000000000 | 401,491 |
| 2024-09-19 | 33,936,304 | 118 | 239,300 | 130,794 | 100.0 | 5737500000000 | 5688500000000 | 162,175 |
| 2024-09-19 | 33,936,304 | 183748 | 1,492,597 | 464,277 | 99.997 | 5797500000000 | 5748250000000 | 1,138,625 |
| 2024-09-19 | 33,936,304 | 393 | 189,067 | 102,291 | 98.798 | 2618200000000 | 2594300000000 | 67,148 |
| 2024-09-19 | 33,936,304 | 4358 | 77,481 | 59,651 | 100.0 | 19966250000000 | 19727250000000 | 46,288 |
| 2024-09-20 | 20,040,158 | 106364 | 461,944 | 322,401 | 100.0 | 20084000000000 | 19860000000000 | 361,098 |
| 2024-09-20 | 20,040,158 | 118 | 10,311 | 6,473 | 100.0 | None | None | 0 |
| 2024-09-20 | 20,040,158 | 183748 | 1,420,838 | 424,977 | 100.0 | 5775000000000 | 5733500000000 | 1,148,724 |
| 2024-09-20 | 20,040,158 | 393 | 191,150 | 101,801 | 98.598 | 2651000000000 | 2627500000000 | 93,076 |
| 2024-09-20 | 20,040,158 | 4358 | 2,186 | 1,758 | 100.0 | None | None | 0 |

## 4. Embudo Liquidity Reversal

Transiciones totales: 459 · señales READY: 6 · rechazos: 103

| Motivo de rechazo | n |
|---|---:|
| DELTA_CONTRARY | 37 |
| NEW_EXTREME_AFTER_RECLAIM | 23 |
| PENETRATION_GT_MAX | 18 |
| NO_CONFIRMATION_10S | 12 |
| NO_RECLAIM_30S | 9 |
| SPREAD_GT_MAX | 3 |
| VOLUME_5S_BELOW_50PCT_MEDIAN | 1 |

## 5. Outcomes contrafactuales (ledger por contrato, EXEC-v1, comisión sintética 6 USD)

| Terminal | n |
|---|---:|
| STOP_TRIGGERED | 4 |
| TARGET_TRIGGERED | 2 |

Trades con P&L: 6 · netos positivos: 2 · P&L neto total: -126.00 USD · media: -21.00 USD · peor: -131.00 · mejor: 144.00

Por dirección: {'LONG': 3, 'SHORT': 3} · por contrato: {'GCZ4': 4, 'NQU4': 1, 'ESZ4': 1}

| Sesión | Contrato | Dir | Nivel | Trigger | Stop | Riesgo | Delta5s | Vol rel | Terminal | Fill | Exit | P&L USD | P&L R | MAE | MFE | Flags |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| 2024-09-09 | GCZ4 | LONG | or_low@25294 | 25297 | 25290 | 7 | +0.50 | 19.58 | STOP_TRIGGERED | 25297 | 25290 | -76.00 | -1.0857142857142856 | -10 | 5 | [] |
| 2024-09-10 | GCZ4 | LONG | or_low@25405 | 25408 | 25399 | 9 | +0.30 | 4.75 | STOP_TRIGGERED | 25408 | 25398 | -106.00 | -1.1777777777777778 | -12 | 12 | [] |
| 2024-09-12 | NQU4 | SHORT | prior_day_high@77174 | 77171 | 77180 | 9 | -0.35 | 2.98 | TARGET_TRIGGERED | 77172 | 77145 | 129.00 | 3.225 | -4 | 28 | [] |
| 2024-09-13 | GCZ4 | SHORT | or_high@26085 | 26082 | 26090 | 8 | -0.70 | 2.30 | STOP_TRIGGERED | 26081 | 26089 | -86.00 | -0.9555555555555556 | -9 | 0 | [] |
| 2024-09-17 | GCZ4 | SHORT | or_high@26037 | 26034 | 26042 | 8 | -0.39 | 0.77 | TARGET_TRIGGERED | 26034 | 26019 | 144.00 | 1.8 | -1 | 16 | [] |
| 2024-09-19 | ESZ4 | LONG | or_low@23073 | 23076 | 23066 | 10 | +0.31 | 1.11 | STOP_TRIGGERED | 23076 | 23066 | -131.00 | -1.048 | -11 | 11 | [] |

## 6. Cuadro de evidencia (protocolo §9)

| Afirmación | Evidencia | Estado |
|---|---|---|
| Ingestión funciona | 30 sesión-contrato procesadas con quality gate; agregados vs ohlcv-1m pendiente de contraste externo | OK |
| Replay causal | tests de determinismo y futuro-no-cambia-pasado en suite; mismo motor en el piloto | OK (suite) |
| Jev integrado | request autenticada con estado sintético (3-oct-2026); datos reales bloqueados por licencia | PARCIAL |
| Probabilidades calibradas | sin dataset suficiente (6 candidatos) | NO |
| Jev aporta valor | experimento B no ejecutado | NO |
| Ejecución funciona | simulada (EXEC-v1); nada real | SIMULADA |
| Agregados consistentes | agresor conocido <= volumen en todos los instrumentos | OK |

---

## 7. Hallazgos de ingeniería (3-oct-2026) y decisiones pendientes

**Factibilidad demostrada.** 30 sesión-contrato (10 sesiones × ES/NQ/GC con selección causal) procesadas de punta a punta: adapter → quality gate → features → régimen/shock/macro → LR-v1 → EXEC-v1, en 20 min con 5 procesos (ES ≈ 240 s, NQ ≈ 260 s, GC ≈ 83 s por sesión en la ventana 08:00–12:00 NY). Volumen diario exacto contra `ohlcv-1d` (70/70), cero resets, cero precios fuera de rejilla, cero revisiones tardías de barras, cero flags `F_SNAPSHOT`/`F_MAYBE_BAD_BOOK`. El 18-sep (marcado *degraded* por el proveedor) no mostró anomalías en la ventana del piloto.

**Bloqueos del gate en la ventana (epochs de 1 s, 30 tareas):**
- `REGIME_UNKNOWN` 4,500 por tarea exactamente = warm-up 08:00–09:15 (15 barras de 5 min). No afecta la ventana de entradas.
- `VOL_SHOCK` 17,219 (ES 6,479 · NQ 7,020 · GC 3,720): el TR de la primera barra tras 09:30 supera 3 × ATR de pre-mercado y bloquea los primeros ~5–10 min de RTH casi todos los días. **Decisión pendiente:** calcular el ATR de referencia del shock solo con barras RTH, o aceptar el bloqueo de apertura como diseño.
- `AGGRESSOR_UNKNOWN_HIGH` 5,966 en **GC** (ES 13, NQ 0): en ventanas trailing de 60 s el gold baja del 95 % con frecuencia (98.4–99 % diario, pero con rachas). **Decisión pendiente:** ventana más larga o umbral por instrumento; hoy GC pierde ~3 min por sesión.
- `STALE_FEED` 42 (solo GC) y `CROSSED_BOOK_PERSISTENT` 4 (ES): marginales.
- `MACRO_BLOCK:CPI` 900 por contrato el 11-sep: cae en warm-up (08:25–08:40).

**Embudo LR-v1:** 109 intentos armados→barridos en 30 sesión-contrato; 6 READY (0.2 por sesión-contrato) y 103 rechazos: DELTA_CONTRARY 37, NEW_EXTREME_AFTER_RECLAIM 23, PENETRATION_GT_MAX 18, NO_CONFIRMATION_10S 12, NO_RECLAIM_30S 9, SPREAD 3, VOLUMEN 1. A este ritmo, el piso de 1,000 candidatos del protocolo exigiría ≈ 5,000 sesión-contrato (≈ 6.5 años de ES/NQ/GC). **Decisión pendiente (antes de comprar historia):** ampliar niveles (swings, VWAP) y/o relajar `max_attempts_per_day`/cooldown en una versión LR-v2 preregistrada; no se tocan parámetros tras ver resultados de test.

**F15 al inicio de RTH:** la mediana de bloques de 5 s de los 30 min previos es de pre-mercado, por lo que el volumen relativo a las 09:35 sale inflado (19.6× en el primer candidato de GC). El filtro de volumen es trivial en la primera media hora. **Decisión pendiente:** referencia solo con bloques desde 09:30 (primer candidato posible ≈ 09:38) para LR-v2.

**Outcomes contrafactuales (6, comisión sintética 6 USD, slippage de salida real del libro):** 2 TARGET (+129, +144) y 4 STOP (−76, −106, −86, −131); neto −126 USD. Cuatro de seis sobre niveles del opening range, dos en GC. **Sin valor estadístico**; sirve solo para comprobar que el simulador etiqueta, mide MAE/MFE y ejecuta stops a peor precio tras la latencia (p.ej. stop 25399 ejecutado a 25398).

**Rollover:** la regla de 5 sesiones al corte (ADR-002) rodó ES/NQ a Z4 el 13-sep; el mercado rodó el 16-sep. El 13-sep se operó Z4 con un cuarto del volumen del U4. Sensibilidad pendiente: 3 sesiones.

**Siguiente puerta (protocolo §6.4, ingeniería → entrenamiento):** causalidad y determinismo pasan en suite; datos/contratos/unidades válidos; etiquetas de referencia auditadas sobre 6 outcomes. Falta: decidir los puntos pendientes de arriba como LR-v2 preregistrada, y adquirir historia suficiente (la muestra actual no da soporte para modelar).

## 8. Sensibilidad preregistrada: controles de datos con referencias solo de RTH (`--variant rth-refs`)

LR-v1 sin cambios. Solo cambian tres controles de datos: ATR de referencia del shock calculado con barras desde 09:30 NY; mediana de F15 con bloques de 5 s desde 09:30 NY; ventana de agresor de GC de 300 s (ES/NQ 60 s). Cobertura medida dentro de la ventana de entradas 09:35–11:30 (69,000 epochs por root = 10 sesiones × 6,900 s).

| Métrica | base | rth-refs |
|---|---:|---:|
| Epochs bloqueados en ventana ES | 2366/69000 (3.4%) | 1517/69000 (2.2%) |
| Epochs bloqueados en ventana NQ | 2710/69000 (3.9%) | 1200/69000 (1.7%) |
| Epochs bloqueados en ventana GC | 3692/69000 (5.4%) | 1075/69000 (1.6%) |
| ventana · VOL_SHOCK | 6140 | 3300 |
| ventana · AGGRESSOR_UNKNOWN_HIGH | 2619 | 483 |
| ventana · CROSSED_BOOK_PERSISTENT / STALE_FEED | 4 / 5 | 4 / 5 |
| Señales READY | 6 | 5 |
| rechazo · VOLUME_REFERENCE_MISSING | 0 | 12 |
| outcomes STOP / TARGET | 4 / 2 | 3 / 2 |
| P&L neto contrafactual (USD) | −126 | −20 |

**Lectura.** Las referencias de RTH recuperan entre 1.2 y 3.8 puntos de cobertura por contrato (GC es el más afectado por el agresor en 60 s). El costo es que F15 no existe hasta 09:38:20 (100 bloques de 5 s desde 09:30): 12 intentos de LR en los primeros minutos se rechazan por `VOLUME_REFERENCE_MISSING`, y desaparece el candidato de GC del 10-sep. La diferencia de P&L (−126 vs −20) es un solo trade y no significa nada. **Decisión para LR-v2 (preregistrar antes de comprar historia):** adoptar rth-refs y decidir si el mínimo de 100 bloques de F15 baja a 60 (09:35) o se mantiene.

**Reproducibilidad en datos reales:** dos corridas independientes de la variante base producen exactamente los mismos 6 candidatos y outcomes.

**Gotcha operativo:** dos corridas del piloto en paralelo (2 × 3 workers) se quedaron sin avanzar durante 35 min (58 s de CPU por worker); una sola corrida con 5 workers termina 30 tareas en 20 min. Correr las variantes en serie.
