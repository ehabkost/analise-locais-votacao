# Seções que mudaram de local de votação entre o 1º e o 2º turno

Fonte: dados abertos do TSE (`eleitorado_local_votacao_{ano}.zip`), processados por `mudancas_secoes.py`.
Seções casadas pela chave UF + município + zona + seção.

| Ano | Tipo | Seções comparadas | Mudou NR_LOCAL_VOTACAO | % | Mudou endereço | % |
|---|---|---:|---:|---:|---:|---:|
| 2010 | Geral | 419.538 | **18** | 0,004% | **116** | 0,028% |
| 2012 | Municipal | 88.285 | **200** | 0,227% | **173** | 0,196% |
| 2014 | Geral | 451.747 | **243** | 0,054% | **129** | 0,029% |
| 2016 | Municipal | 93.253 | **2.480** | 2,659% | **2.369** | 2,540% |
| 2018 | Geral | 481.863 | **618** | 0,128% | **466** | 0,097% |
| 2020 | Municipal | 113.764 | **58** | 0,051% | **95** | 0,084% |
| 2022 | Geral | 496.856 | **1.387** | 0,279% | **620** | 0,125% |
| 2024 | Municipal | 98.863 | **126** | 0,127% | **146** | 0,148% |
| 2026 | Geral | 517.179 | **2.053** | 0,397% | **933** | 0,180% |

Totais e listas detalhadas (UFs, municípios, zonas, seções, eleitores, locais, endereços) por ano: [`resultados/`](resultados/TOTAIS.md). Script: [`mudancas_secoes.py`](mudancas_secoes.py).

## Critérios

- **Mudou NR_LOCAL_VOTACAO**: `NR_LOCAL_VOTACAO` diferente entre os turnos. Pode ser só renumeração do local, sem mudança física.
- **Mudou endereço**: endereço normalizado (sem acentos/pontuação/prefixo de logradouro/telefone) E CEP diferentes. Independe do número do local.
- O texto bruto de `DS_ENDERECO` não é usado isoladamente: a formatação varia entre turnos ("R." x "RUA", "S/N" x "SN"…) e gera falsos positivos (ex.: 2010 daria 1.188 seções em vez de 116).

## Ressalvas

- Nas eleições municipais só há 2º turno nos municípios com disputa; comparam-se apenas as seções deles.
- Os dados de 2026 foram gerados em 17/10/2026 e podem estar desatualizados.
- Em 2010 uma seção duplicada foi descartada.
