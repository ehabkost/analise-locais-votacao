#!/usr/bin/env python3
"""Baixa os dados de locais de votação do TSE, extrai e calcula quantas seções
mudaram de local de votação entre o 1º e o 2º turno em cada eleição.

Uso: python3 mudancas_secoes.py [--dir DIRETORIO] [--anos 2018 2022 ...] [--listar > saida.md | --totais DIR]
A saída (stdout) é Markdown; o progresso vai para stderr.
Só usa a biblioteca padrão. Zips já baixados são reaproveitados.
"""
import argparse
import contextlib
import csv
import io
import os
import re
import sys
import unicodedata
import urllib.request
import zipfile

URL = ("https://cdn.tse.jus.br/estatistica/sead/odsele/"
       "eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip")
ANOS = [2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026]
CHAVE = ("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")

csv.field_size_limit(sys.maxsize)


def baixar(ano, destino):
    zpath = os.path.join(destino, f"eleitorado_local_votacao_{ano}.zip")
    if os.path.exists(zpath) and zipfile.is_zipfile(zpath):
        return zpath
    url = URL.format(ano=ano)
    print(f"  baixando {url}", file=sys.stderr)
    tmp = zpath + ".part"
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, zpath)
    return zpath


def extrair(zpath, ano, destino):
    """Extrai o CSV nacional (em 2026 há um CSV por UF e um _BRASIL)."""
    with zipfile.ZipFile(zpath) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        alvo = next((n for n in csvs if n.endswith("_BRASIL.csv")), csvs[0])
        out = os.path.join(destino, alvo)
        if not os.path.exists(out):
            print(f"  extraindo {alvo}", file=sys.stderr)
            z.extract(alvo, destino)
        return out


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\bFONE.*$", "", s)
    s = re.sub(r"[^A-Z0-9]+", "", s)
    return re.sub(r"^(RUA|AVENIDA|AV|R|TRAVESSA|ESTRADA|PRACA|RODOVIA)", "", s)


def ler(path, detalhes=False):
    """Retorna {turno: {chave: (nr_local, endereco_normalizado, cep[, extras])}}.

    Com detalhes=True, inclui também (município, nome do local, endereço,
    eleitores da seção)."""
    turnos = {}
    with open(path, encoding="latin1", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            k = tuple(r[c] for c in CHAVE)
            v = (r["NR_LOCAL_VOTACAO"], norm(r["DS_ENDERECO"]), r["NR_CEP"])
            if detalhes:
                v += (r["NM_MUNICIPIO"], r["NM_LOCAL_VOTACAO"], r["DS_ENDERECO"],
                      int(r["QT_ELEITOR_SECAO"] or 0))
            turnos.setdefault(r["NR_TURNO"], {}).setdefault(k, v)
    return turnos


def comparar(turnos):
    """Retorna (n_comparadas, [(chave, mudou_nr, mudou_end, v1, v2), ...],
    eleitorado_por_uf). O eleitorado só é calculado com ler(detalhes=True)."""
    t1, t2 = turnos["1"], turnos["2"]
    comuns = t1.keys() & t2.keys()
    mudancas = []
    eleit_uf = {}
    for k in sorted(comuns, key=lambda k: (k[0], k[1], int(k[2]), int(k[3]))):
        v1, v2 = t1[k], t2[k]
        if len(v1) > 6:
            eleit_uf[k[0]] = eleit_uf.get(k[0], 0) + v1[6]
        nr = v1[0] != v2[0]
        end = v1[1] != v2[1] and v1[2] != v2[2]
        if nr or end:
            mudancas.append((k, nr, end, v1, v2))
    return len(comuns), mudancas, eleit_uf


def br(x, casas=0):
    """Formata número no padrão brasileiro (1.234,567)."""
    return f"{x:,.{casas}f}".translate(str.maketrans(",.", ".,"))


def cel(x):
    return " ".join(x.split()).replace("|", "\\|")


def listar_md(ano, mudancas):
    print(f"\n## {ano} - seções que mudaram ({br(len(mudancas))})\n")
    print("| UF | Município | Zona | Seção | Eleitores | NR_LOCAL 1º→2º | NR | End. "
          "| Local 1º turno | Endereço 1º turno | Local 2º turno | Endereço 2º turno |")
    print("|---|---|---:|---:|---:|---|:-:|:-:|---|---|---|---|")
    for (uf, _, zona, secao), nr, end, v1, v2 in mudancas:
        print(f"| {uf} | {cel(v1[3])} | {zona} | {secao} | {br(v1[6])} | {v1[0]}→{v2[0]} "
              f"| {'✓' if nr else ''} | {'✓' if end else ''} "
              f"| {cel(v1[4])} | {cel(v1[5])} | {cel(v2[4])} | {cel(v2[5])} |")


BASES = (("NR_LOCAL_VOTACAO", 1, "mudou NR_LOCAL_VOTACAO"),
         ("endereço", 2, "mudou endereço (endereço normalizado E CEP diferentes)"))


def afetados(mudancas, idx):
    """Agrega as seções afetadas segundo o critério (idx=1: NR; idx=2: endereço)."""
    a = dict(ufs={}, muns={}, zonas={}, secoes=[], eleitores=0, locais={}, ends={})
    for m in mudancas:
        if not m[idx]:
            continue
        (uf, cd, zona, secao), v1, v2 = m[0], m[3], m[4]
        eleit = v1[6]
        a["eleitores"] += eleit
        for d, k in ((a["ufs"], uf), (a["muns"], (uf, cd, v1[3])),
                     (a["zonas"], (uf, int(zona)))):
            c = d.setdefault(k, [0, 0])
            c[0] += 1
            c[1] += eleit
        a["secoes"].append((uf, v1[3], int(zona), int(secao), eleit))
        for papel, v in (("origem", v1), ("destino", v2)):
            l = a["locais"].setdefault((uf, cd, v[0], norm(v[4])), [v[3], v[4], set(), 0])
            l[2].add(papel)
            e = a["ends"].setdefault((uf, cd, v[1], v[2]), [v[3], v[5], v[2], set(), 0])
            e[3].add(papel)
        # conta a seção uma vez por local/endereço (origem e destino distintos)
        for k in {(uf, cd, v1[0], norm(v1[4])), (uf, cd, v2[0], norm(v2[4]))}:
            a["locais"][k][3] += 1
        for k in {(uf, cd, v1[1], v1[2]), (uf, cd, v2[1], v2[2])}:
            a["ends"][k][4] += 1
    return a


def tabela(cabecalho, alinh, linhas):
    print("| " + " | ".join(cabecalho) + " |")
    print("|" + "|".join({"l": "---", "r": "---:"}[x] for x in alinh) + "|")
    for l in linhas:
        print("| " + " | ".join(str(x) for x in l) + " |")
    print()


def val(d, k, i):
    """Valor formatado de d[k][i], ou '–' se k não é afetado por esse critério."""
    return br(d[k][i]) if k in d else "–"


def papeis(d, k, i):
    return "/".join(sorted(d[k][i])) if k in d else "–"


def gerar_arquivos(resultados, saida):
    """Grava TOTAIS.md e uma lista detalhada por item afetado, cada uma com uma
    seção por ano e colunas (NR) / (End.) para os dois critérios."""
    por_ano = {ano: (mud, eleit_uf) for ano, n, mud, eleit_uf in resultados
               if n is not None}
    agg = {ano: [afetados(mud, idx) for _, idx, _ in BASES]
           for ano, (mud, _) in por_ano.items()}
    aviso = ("Colunas (NR) = critério mudou NR_LOCAL_VOTACAO; (End.) = critério "
             "mudou endereço. `–` = não afetado por aquele critério.\n")

    def escrever(nome, fn):
        with open(os.path.join(saida, nome), "w", encoding="utf-8") as f, \
                contextlib.redirect_stdout(f):
            fn()
        print(f"  escrito {nome}", file=sys.stderr)

    def totais():
        print("# Totais de seções que mudaram entre o 1º e o 2º turno\n")
        print("Eleitores = soma de `QT_ELEITOR_SECAO` (1º turno) das seções "
              "afetadas. Locais e endereços afetados incluem os de origem "
              "(1º turno) e os de destino (2º turno). Um local é identificado por "
              "NR_LOCAL_VOTACAO + nome (o mesmo número pode designar locais "
              "diferentes nos dois turnos); um endereço, por endereço normalizado "
              "+ CEP.\n")
        for (_, _, desc), k in zip(BASES, (0, 1)):
            print(f"## Critério: {desc}\n")
            linhas = []
            for ano in por_ano:
                a = agg[ano][k]
                linhas.append((ano, *(br(x) for x in (
                    len(a["ufs"]), len(a["muns"]), len(a["zonas"]),
                    len(a["secoes"]), a["eleitores"], len(a["locais"]),
                    len(a["ends"])))))
            tabela(["Ano", "UFs", "Municípios", "Zonas", "Seções", "Eleitores",
                    "Locais", "Endereços"], "l" + "r" * 7, linhas)
        print("Listas detalhadas por ano: `UFS.md`, `MUNICIPIOS.md`, `ZONAS.md`, "
              "`SECOES.md`, `ELEITORES.md`, `LOCAIS.md`, `ENDERECOS.md`.")

    def por_item(titulo, chave, cab, alinh, ident, ordem, extra, ealinh, linha_extra):
        """Arquivo com uma seção por ano para os itens de a[chave]."""
        print(f"# {titulo} afetados, por ano\n")
        print(aviso)
        for ano in por_ano:
            nr, en = agg[ano]
            print(f"## {ano} - {titulo.lower()} ({br(len(nr[chave]))} por "
                  f"NR_LOCAL_VOTACAO, {br(len(en[chave]))} por endereço)\n")
            chaves = sorted(set(nr[chave]) | set(en[chave]),
                            key=lambda k: ordem(k, nr[chave], en[chave]))
            tabela(cab + extra, alinh + ealinh,
                   [ident(k, nr[chave], en[chave]) + list(linha_extra(nr[chave], en[chave], k))
                    for k in chaves])

    def info(k, dnr, den):
        return dnr[k] if k in dnr else den[k]

    def secoes_eleit(dnr, den, k):
        return (val(dnr, k, 0), val(den, k, 0), val(dnr, k, 1), val(den, k, 1))

    SE = ["Seções (NR)", "Seções (End.)", "Eleitores (NR)", "Eleitores (End.)"]

    def ufs():
        print("# UFs afetadas, por ano\n")
        print(aviso)
        for ano in por_ano:
            nr, en = agg[ano]
            print(f"## {ano} - UFs ({br(len(nr['ufs']))} por NR_LOCAL_VOTACAO, "
                  f"{br(len(en['ufs']))} por endereço)\n")

            def cont(a):
                c = {}
                for (uf, _, _) in a["muns"]:
                    c.setdefault(uf, [0, 0, 0])[0] += 1
                for (uf, _) in a["zonas"]:
                    c[uf][1] += 1
                for uf, (ns, _) in a["ufs"].items():
                    c[uf][2] = ns
                return c
            cn, ce = cont(nr), cont(en)
            linhas = []
            for uf in sorted(set(cn) | set(ce)):
                linha = [uf]
                for i in range(3):
                    linha += [br(cn[uf][i]) if uf in cn else "–",
                              br(ce[uf][i]) if uf in ce else "–"]
                linhas.append(linha)
            tabela(["UF", "Municípios (NR)", "Municípios (End.)", "Zonas (NR)",
                    "Zonas (End.)", "Seções (NR)", "Seções (End.)"], "lrrrrrr", linhas)

    def muns():
        por_item("Municípios", "muns", ["UF", "Município"], "ll",
                 lambda k, a, b: [k[0], cel(k[2])], lambda k, a, b: (k[0], k[2]),
                 SE, "rrrr", secoes_eleit)

    def zonas():
        por_item("Zonas eleitorais", "zonas", ["UF", "Zona"], "lr",
                 lambda k, a, b: [k[0], k[1]], lambda k, a, b: k,
                 SE, "rrrr", secoes_eleit)

    def locais():
        por_item("Locais de votação", "locais",
                 ["UF", "Município", "NR_LOCAL", "Local"], "llrl",
                 lambda k, a, b: [k[0], cel(info(k, a, b)[0]), k[2], cel(info(k, a, b)[1])],
                 lambda k, a, b: (k[0], info(k, a, b)[0], int(k[2])),
                 ["Papel (NR)", "Papel (End.)", "Seções (NR)", "Seções (End.)"], "llrr",
                 lambda a, b, k: (papeis(a, k, 2), papeis(b, k, 2), val(a, k, 3), val(b, k, 3)))

    def enderecos():
        por_item("Endereços", "ends",
                 ["UF", "Município", "Endereço", "CEP"], "lllr",
                 lambda k, a, b: [k[0], cel(info(k, a, b)[0]), cel(info(k, a, b)[1]),
                                  info(k, a, b)[2]],
                 lambda k, a, b: (k[0], info(k, a, b)[0], info(k, a, b)[1]),
                 ["Papel (NR)", "Papel (End.)", "Seções (NR)", "Seções (End.)"], "llrr",
                 lambda a, b, k: (papeis(a, k, 3), papeis(b, k, 3), val(a, k, 4), val(b, k, 4)))

    def eleitores():
        print("# Eleitores afetados, por ano\n")
        print("Eleitores = soma de `QT_ELEITOR_SECAO` (1º turno) das seções "
              "afetadas. % = sobre o eleitorado das seções comparadas na UF.\n")
        print(aviso)
        for ano in por_ano:
            nr, en = agg[ano]
            eleit_uf = por_ano[ano][1]
            print(f"## {ano} - eleitores ({br(nr['eleitores'])} por NR_LOCAL_VOTACAO, "
                  f"{br(en['eleitores'])} por endereço)\n")
            linhas = []
            for uf in sorted(set(nr["ufs"]) | set(en["ufs"])):
                linha = [uf, br(eleit_uf[uf])]
                for a in (nr, en):
                    el = a["ufs"][uf][1] if uf in a["ufs"] else 0
                    linha += [br(el), br(100 * el / eleit_uf[uf], 3) + "%"]
                linhas.append(linha)
            tabela(["UF", "Eleitorado da UF", "Afetados (NR)", "% (NR)",
                    "Afetados (End.)", "% (End.)"], "lrrrrr", linhas)

    def secoes():
        print("# Seções afetadas, por ano")
        for ano, n, mud, _ in resultados:
            if n is not None:
                listar_md(ano, mud)

    os.makedirs(saida, exist_ok=True)
    for nome, fn in (("TOTAIS.md", totais), ("UFS.md", ufs), ("MUNICIPIOS.md", muns),
                     ("ZONAS.md", zonas), ("SECOES.md", secoes),
                     ("ELEITORES.md", eleitores), ("LOCAIS.md", locais),
                     ("ENDERECOS.md", enderecos)):
        escrever(nome, fn)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--anos", type=int, nargs="*", default=ANOS)
    p.add_argument("--listar", action="store_true",
                   help="lista exatamente quais seções mudaram, por ano")
    p.add_argument("--totais", metavar="DIR",
                   help="grava TOTAIS.md e os demais .md (UFS, MUNICIPIOS, ZONAS, "
                        "SECOES, ELEITORES, LOCAIS, ENDERECOS) em DIR")
    a = p.parse_args()
    os.makedirs(a.dir, exist_ok=True)

    resultados = []
    for ano in a.anos:
        print(f"{ano}:", file=sys.stderr)
        csv_path = extrair(baixar(ano, a.dir), ano, a.dir)
        turnos = ler(csv_path, a.listar or bool(a.totais))
        if "2" not in turnos:
            resultados.append((ano, None, [], {}))
            continue
        resultados.append((ano,) + comparar(turnos))

    if a.totais:
        gerar_arquivos(resultados, a.totais)
        return

    print("# Seções que mudaram entre o 1º e o 2º turno\n")
    print("| Ano | Comparadas | Mudou NR_LOCAL_VOTACAO | % | Mudou endereço | % |")
    print("|---|---:|---:|---:|---:|---:|")
    for ano, n, mud, _ in resultados:
        if n is None:
            print(f"| {ano} | (sem 2º turno) | | | | |")
            continue
        loc = sum(m[1] for m in mud)
        end = sum(m[2] for m in mud)
        print(f"| {ano} | {br(n)} | {br(loc)} | {br(100 * loc / n, 3)}% "
              f"| {br(end)} | {br(100 * end / n, 3)}% |")
    print("\n- **Mudou NR_LOCAL_VOTACAO**: número do local de votação diferente.")
    print("- **Mudou endereço**: endereço normalizado E CEP diferentes.")

    if a.listar:
        for ano, n, mud, _ in resultados:
            if n is not None:
                listar_md(ano, mud)


if __name__ == "__main__":
    main()
