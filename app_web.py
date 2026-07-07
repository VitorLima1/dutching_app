from __future__ import annotations

import json
from itertools import product
from decimal import Decimal
from pathlib import Path
from typing import Any

import streamlit as st

from dutching import DutchingValidationError, calcular_dutching


ROOT_DIR = Path(__file__).resolve().parent
PAYLOAD_EXEMPLO = ROOT_DIR / "examples" / "payload_exemplo.json"
ORDEM_RESULTADOS = ("1", "X", "2")
CENT = Decimal("0.01")


def carregar_payload_exemplo() -> dict[str, Any]:
    return json.loads(PAYLOAD_EXEMPLO.read_text(encoding="utf-8"))


def descrever_resultado(jogo: dict[str, Any], resultado: str) -> str:
    if resultado == "1":
        return f"{jogo['mandante']} vence"
    if resultado.upper() == "X":
        return f"{jogo['mandante']} x {jogo['visitante']} empata"
    if resultado == "2":
        return f"{jogo['visitante']} vence"
    return resultado


def resultados_ordenados(jogo: dict[str, Any]) -> list[str]:
    odds = jogo["odds"]
    resultados_padrao = [resultado for resultado in ORDEM_RESULTADOS if resultado in odds]
    resultados_extras = sorted(resultado for resultado in odds if resultado not in ORDEM_RESULTADOS)
    return resultados_padrao + resultados_extras


def gerar_duplas_possiveis(jogos: list[dict[str, Any]]) -> list[dict[str, str]]:
    if len(jogos) != 2:
        raise ValueError("A tela de dutching espera exatamente dois jogos para gerar duplas.")

    jogo_1, jogo_2 = jogos
    return [
        {jogo_1["id"]: resultado_1, jogo_2["id"]: resultado_2}
        for resultado_1, resultado_2 in product(
            resultados_ordenados(jogo_1),
            resultados_ordenados(jogo_2),
        )
    ]


def label_dupla(dupla: dict[str, str], jogos_por_id: dict[str, dict[str, Any]]) -> str:
    partes: list[str] = []
    odds: list[Decimal] = []

    for jogo_id, resultado in dupla.items():
        jogo = jogos_por_id[jogo_id]
        odd = Decimal(str(jogo["odds"][resultado]))
        partes.append(f"{descrever_resultado(jogo, resultado)} ({odd:.2f})")
        odds.append(odd)

    odd_combinada = odds[0] * odds[1]
    return f"{' + '.join(partes)} | Odd combinada: {odd_combinada:.2f}"


def odd_combinada_dupla(dupla: dict[str, str], jogos_por_id: dict[str, dict[str, Any]]) -> Decimal:
    odd_combinada = Decimal("1")
    for jogo_id, resultado in dupla.items():
        odd_combinada *= Decimal(str(jogos_por_id[jogo_id]["odds"][resultado]))
    return odd_combinada


def montar_df_calculo(
    duplas: list[dict[str, str]],
    jogos_por_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "dupla": dupla,
                "odd_combinada": odd_combinada_dupla(dupla, jogos_por_id),
            }
            for dupla in duplas
        ],
        key=lambda linha: linha["odd_combinada"],
        reverse=True,
    )


def ordenar_duplas_por_odd_decrescente(
    duplas: list[dict[str, str]],
    jogos_por_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    return [linha["dupla"] for linha in montar_df_calculo(duplas, jogos_por_id)]


def chave_dupla(index: int, dupla: dict[str, str]) -> str:
    partes = [f"{jogo_id}:{resultado}" for jogo_id, resultado in dupla.items()]
    return f"dupla_{index}_{'_'.join(partes)}"


def filtrar_duplas_marcadas(
    duplas_disponiveis: list[dict[str, str]],
    estados_duplas: dict[str, bool],
) -> list[dict[str, str]]:
    return [
        dupla
        for index, dupla in enumerate(duplas_disponiveis, start=1)
        if estados_duplas.get(chave_dupla(index, dupla)) is True
    ]


def nome_dupla(bilhete: dict[str, Any]) -> str:
    descricoes = [perna["descricao"] for perna in bilhete["pernas"]]
    return " + ".join(descricoes)


def formatar_moeda(valor: str | Decimal) -> str:
    return f"R$ {Decimal(str(valor)):.2f}"


def linhas_tabela(bilhetes: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Dupla": nome_dupla(bilhete),
            "Valor a Apostar": formatar_moeda(bilhete["valor_apostado"]),
            "Retorno Potencial": formatar_moeda(bilhete["retorno_potencial"]),
            "Lucro Real": formatar_moeda(bilhete["lucro_sobre_banca"]),
        }
        for bilhete in bilhetes
    ]


def lucro_minimo(bilhetes: list[dict[str, Any]]) -> Decimal:
    if not bilhetes:
        return Decimal("0")
    return min(Decimal(str(bilhete["lucro_sobre_banca"])) for bilhete in bilhetes)


def montar_travas_pre_alocadas(
    df_calculo: list[dict[str, Any]],
    banca_total: float,
    valor_travado_maior_odd: float = 0.0,
    valor_travado_segunda_maior_odd: float = 0.0,
    valor_travado_menor_odd: float = 0.0,
) -> tuple[list[dict[str, Any]], Decimal, str | None]:
    banca_disponivel = Decimal(f"{banca_total:.2f}")
    travas: list[dict[str, Any]] = []
    duplas_travadas: set[tuple[tuple[str, str], ...]] = set()

    def registrar_trava(dupla: dict[str, str], valor: float, rotulo: str) -> Decimal:
        valor_decimal = Decimal(f"{valor:.2f}").quantize(CENT)
        if valor_decimal <= 0:
            return Decimal("0")

        chave = tuple(sorted(dupla.items()))
        if chave in duplas_travadas:
            return Decimal("0")

        duplas_travadas.add(chave)
        travas.append(
            {
                "selecoes": dupla,
                "valor": f"{valor_decimal:.2f}",
                "rotulo": rotulo,
            }
        )
        return valor_decimal

    if valor_travado_maior_odd > 0:
        banca_disponivel -= registrar_trava(
            df_calculo[0]["dupla"],
            valor_travado_maior_odd,
            "maior odd",
        )

    if valor_travado_segunda_maior_odd > 0:
        if len(df_calculo) < 2:
            return (
                travas,
                banca_disponivel,
                "Valor travado na segunda maior odd requer pelo menos dois bilhetes selecionados.",
            )
        banca_disponivel -= registrar_trava(
            df_calculo[1]["dupla"],
            valor_travado_segunda_maior_odd,
            "segunda maior odd",
        )

    if valor_travado_menor_odd > 0:
        banca_disponivel -= registrar_trava(
            df_calculo[-1]["dupla"],
            valor_travado_menor_odd,
            "menor odd",
        )

    if banca_disponivel < 0:
        return travas, banca_disponivel, "Valores travados ultrapassam a banca total."

    return travas, banca_disponivel, None


def montar_payload_calculo(
    payload_base: dict[str, Any],
    banca_total: float,
    minimo_por_bilhete: float,
    duplas_escolhidas: list[dict[str, str]],
    valor_travado_menor_odd: float = 0.0,
    valor_travado_maior_odd: float = 0.0,
    valor_travado_segunda_maior_odd: float = 0.0,
    apostas_travadas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "banca_total": f"{banca_total:.2f}",
        "minimo_por_bilhete": f"{minimo_por_bilhete:.2f}",
        "valor_travado_menor_odd": f"{valor_travado_menor_odd:.2f}",
        "valor_travado_maior_odd": f"{valor_travado_maior_odd:.2f}",
        "valor_travado_segunda_maior_odd": f"{valor_travado_segunda_maior_odd:.2f}",
        "apostas_travadas": apostas_travadas or [],
        "jogos": payload_base["jogos"],
        "duplas_escolhidas": duplas_escolhidas,
    }


def exibir_jogos(jogos: list[dict[str, Any]]) -> None:
    st.subheader("Jogos disponíveis")
    for jogo in jogos:
        with st.expander(f"{jogo['mandante']} x {jogo['visitante']}", expanded=True):
            st.write(
                {
                    "Mandante": f"{jogo['mandante']} ({jogo['odds']['1']:.2f})",
                    "Empate": f"X ({jogo['odds']['X']:.2f})",
                    "Visitante": f"{jogo['visitante']} ({jogo['odds']['2']:.2f})",
                }
            )


def exibir_resultado(resultado: dict[str, Any]) -> None:
    st.subheader("Distribuição calculada")

    if resultado["descartados"]:
        descartados = ", ".join(nome_dupla(bilhete) for bilhete in resultado["descartados"])
        st.warning(f"Bilhetes descartados para fechar a conta: {descartados}")

    for alerta in resultado["alertas"]:
        st.warning(alerta)

    if not resultado["viavel"]:
        st.error("Não foi possível encontrar uma distribuição viável com os parâmetros informados.")
        return

    total_alocado, lucro_garantido = st.columns(2)
    total_alocado.metric("Total Alocado", formatar_moeda(resultado["banca_alocada"]))
    lucro_garantido.metric(
        "Lucro Mínimo Garantido",
        formatar_moeda(lucro_minimo(resultado["bilhetes"])),
    )

    st.dataframe(linhas_tabela(resultado["bilhetes"]), width="stretch", hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Dutching Betapp", layout="wide")

    payload_base = carregar_payload_exemplo()
    jogos = payload_base["jogos"]
    duplas_disponiveis = gerar_duplas_possiveis(jogos)
    jogos_por_id = {jogo["id"]: jogo for jogo in jogos}

    st.title("Dutching Betapp")
    st.caption("Distribuição proporcional de banca para duplas combinadas.")

    with st.sidebar:
        st.header("Configuração")
        banca_total = st.number_input(
            "Valor da Banca Total",
            min_value=0.01,
            value=10.00,
            step=0.50,
            format="%.2f",
        )
        minimo_por_bilhete = st.number_input(
            "Valor Mínimo por Bilhete",
            min_value=0.01,
            value=0.50,
            step=0.10,
            format="%.2f",
        )
        valor_travado_menor_odd = st.number_input(
            "Travar Valor na Menor Odd (Opcional)",
            min_value=0.00,
            value=0.00,
            step=0.50,
            format="%.2f",
        )
        valor_travado_maior_odd = st.number_input(
            "Travar Valor na Maior Odd (Opcional)",
            min_value=0.00,
            value=0.00,
            step=0.50,
            format="%.2f",
        )
        valor_travado_segunda_maior_odd = st.number_input(
            "Travar Valor na segunda Maior Odd (Opcional)",
            min_value=0.00,
            value=0.00,
            step=0.01,
            format="%.2f",
        )

    exibir_jogos(jogos)

    st.subheader("Duplas para calcular")
    with st.form("form_duplas"):
        for index, dupla in enumerate(duplas_disponiveis, start=1):
            chave = chave_dupla(index, dupla)
            if chave not in st.session_state:
                st.session_state[chave] = True
            st.checkbox(
                label_dupla(dupla, jogos_por_id),
                key=chave,
            )

        calcular = st.form_submit_button("Calcular Distribuição", type="primary")

    if not calcular:
        return

    estados_duplas = {
        chave_dupla(index, dupla): bool(st.session_state.get(chave_dupla(index, dupla), False))
        for index, dupla in enumerate(duplas_disponiveis, start=1)
    }
    duplas_selecionadas = filtrar_duplas_marcadas(duplas_disponiveis, estados_duplas)

    if not duplas_selecionadas:
        st.warning("Selecione pelo menos uma dupla para calcular.")
        return

    df_calculo = montar_df_calculo(duplas_selecionadas, jogos_por_id)
    duplas_para_calculo = [linha["dupla"] for linha in df_calculo]
    apostas_travadas, _banca_disponivel, erro_travas = montar_travas_pre_alocadas(
        df_calculo,
        banca_total,
        valor_travado_maior_odd,
        valor_travado_segunda_maior_odd,
        valor_travado_menor_odd,
    )

    if erro_travas is not None:
        st.warning(erro_travas)
        return

    payload_calculo = montar_payload_calculo(
        payload_base,
        banca_total,
        minimo_por_bilhete,
        duplas_para_calculo,
        valor_travado_menor_odd,
        valor_travado_maior_odd,
        valor_travado_segunda_maior_odd,
        apostas_travadas,
    )

    try:
        resultado = calcular_dutching(payload_calculo)
    except DutchingValidationError as exc:
        st.error(f"Erro de validação: {exc}")
        return

    exibir_resultado(resultado)


if __name__ == "__main__":
    main()
