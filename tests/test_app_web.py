from __future__ import annotations

import unittest
from decimal import Decimal

from app_web import (
    chave_dupla,
    filtrar_duplas_marcadas,
    gerar_duplas_possiveis,
    label_dupla,
    montar_df_calculo,
    montar_travas_pre_alocadas,
    montar_payload_calculo,
    odd_combinada_dupla,
    ordenar_duplas_por_odd_decrescente,
)


def jogos_exemplo() -> list[dict]:
    return [
        {
            "id": "jogo_1",
            "mandante": "Argentina",
            "visitante": "Egito",
            "odds": {"1": 1.33, "X": 4.75, "2": 11.00},
        },
        {
            "id": "jogo_2",
            "mandante": "Suíça",
            "visitante": "Colômbia",
            "odds": {"1": 3.50, "X": 3.10, "2": 2.25},
        },
    ]


class AppWebCombinacoesTest(unittest.TestCase):
    def test_gera_matriz_completa_de_nove_duplas(self) -> None:
        duplas = gerar_duplas_possiveis(jogos_exemplo())

        self.assertEqual(len(duplas), 9)
        self.assertEqual(duplas[0], {"jogo_1": "1", "jogo_2": "1"})
        self.assertEqual(duplas[-1], {"jogo_1": "2", "jogo_2": "2"})
        self.assertIn({"jogo_1": "X", "jogo_2": "X"}, duplas)

    def test_label_exibe_novas_selecoes_e_odd_combinada(self) -> None:
        jogos = jogos_exemplo()
        duplas = gerar_duplas_possiveis(jogos)
        jogos_por_id = {jogo["id"]: jogo for jogo in jogos}

        label = label_dupla(duplas[1], jogos_por_id)

        self.assertEqual(
            label,
            "Argentina vence (1.33) + Suíça x Colômbia empata (3.10) | Odd combinada: 4.12",
        )

    def test_payload_envia_exatamente_duplas_marcadas(self) -> None:
        payload_base = {"jogos": jogos_exemplo()}
        duplas_marcadas = [
            {"jogo_1": "1", "jogo_2": "X"},
            {"jogo_1": "2", "jogo_2": "2"},
        ]
        apostas_travadas = [
            {
                "selecoes": {"jogo_1": "2", "jogo_2": "2"},
                "valor": "1.25",
                "rotulo": "segunda maior odd",
            }
        ]

        payload = montar_payload_calculo(
            payload_base,
            10.0,
            0.5,
            duplas_marcadas,
            2.0,
            1.5,
            1.25,
            apostas_travadas,
        )

        self.assertEqual(payload["duplas_escolhidas"], duplas_marcadas)
        self.assertEqual(payload["banca_total"], "10.00")
        self.assertEqual(payload["minimo_por_bilhete"], "0.50")
        self.assertEqual(payload["valor_travado_menor_odd"], "2.00")
        self.assertEqual(payload["valor_travado_maior_odd"], "1.50")
        self.assertEqual(payload["valor_travado_segunda_maior_odd"], "1.25")
        self.assertEqual(payload["apostas_travadas"], apostas_travadas)

    def test_ordena_duplas_marcadas_por_odd_decrescente(self) -> None:
        jogos = jogos_exemplo()
        duplas = gerar_duplas_possiveis(jogos)
        jogos_por_id = {jogo["id"]: jogo for jogo in jogos}

        ordenadas = ordenar_duplas_por_odd_decrescente(duplas, jogos_por_id)

        self.assertEqual(ordenadas[0], {"jogo_1": "2", "jogo_2": "1"})
        self.assertEqual(odd_combinada_dupla(ordenadas[0], jogos_por_id), Decimal("38.5000"))
        self.assertEqual(ordenadas[1], {"jogo_1": "2", "jogo_2": "X"})
        self.assertEqual(odd_combinada_dupla(ordenadas[1], jogos_por_id), Decimal("34.1000"))

    def test_monta_travas_pre_alocadas_maior_e_segunda_maior_odd(self) -> None:
        jogos = jogos_exemplo()
        duplas = gerar_duplas_possiveis(jogos)
        jogos_por_id = {jogo["id"]: jogo for jogo in jogos}
        df_calculo = montar_df_calculo(duplas, jogos_por_id)

        travas, banca_disponivel, erro = montar_travas_pre_alocadas(
            df_calculo,
            10.0,
            valor_travado_maior_odd=1.50,
            valor_travado_segunda_maior_odd=1.25,
        )

        self.assertIsNone(erro)
        self.assertEqual(banca_disponivel, Decimal("7.25"))
        self.assertEqual(
            travas,
            [
                {
                    "selecoes": {"jogo_1": "2", "jogo_2": "1"},
                    "valor": "1.50",
                    "rotulo": "maior odd",
                },
                {
                    "selecoes": {"jogo_1": "2", "jogo_2": "X"},
                    "valor": "1.25",
                    "rotulo": "segunda maior odd",
                },
            ],
        )

    def test_monta_trava_segunda_maior_com_subset_ativo_por_odd(self) -> None:
        jogos = jogos_exemplo()
        jogos_por_id = {jogo["id"]: jogo for jogo in jogos}
        duplas_marcadas = [
            {"jogo_1": "1", "jogo_2": "2"},
            {"jogo_1": "X", "jogo_2": "1"},
            {"jogo_1": "X", "jogo_2": "2"},
            {"jogo_1": "1", "jogo_2": "1"},
        ]
        df_calculo = montar_df_calculo(duplas_marcadas, jogos_por_id)

        travas, banca_disponivel, erro = montar_travas_pre_alocadas(
            df_calculo,
            10.0,
            valor_travado_maior_odd=1.50,
            valor_travado_segunda_maior_odd=1.25,
        )

        self.assertIsNone(erro)
        self.assertEqual(banca_disponivel, Decimal("7.25"))
        self.assertEqual(df_calculo[0]["dupla"], {"jogo_1": "X", "jogo_2": "1"})
        self.assertEqual(df_calculo[0]["odd_combinada"], Decimal("16.6250"))
        self.assertEqual(df_calculo[1]["dupla"], {"jogo_1": "X", "jogo_2": "2"})
        self.assertEqual(df_calculo[1]["odd_combinada"], Decimal("10.6875"))
        self.assertEqual(
            travas[1],
            {
                "selecoes": {"jogo_1": "X", "jogo_2": "2"},
                "valor": "1.25",
                "rotulo": "segunda maior odd",
            },
        )

    def test_trava_pre_alocada_segunda_maior_exige_dois_bilhetes(self) -> None:
        travas, _banca_disponivel, erro = montar_travas_pre_alocadas(
            [{"dupla": {"jogo_1": "1", "jogo_2": "2"}, "odd_combinada": Decimal("2.9925")}],
            10.0,
            valor_travado_segunda_maior_odd=1.00,
        )

        self.assertEqual(travas, [])
        self.assertEqual(
            erro,
            "Valor travado na segunda maior odd requer pelo menos dois bilhetes selecionados.",
        )

    def test_filtra_duplas_usando_estado_explicitamente_true(self) -> None:
        duplas = gerar_duplas_possiveis(jogos_exemplo())
        estados = {
            chave_dupla(1, duplas[0]): True,
            chave_dupla(2, duplas[1]): False,
            chave_dupla(4, duplas[3]): True,
        }

        selecionadas = filtrar_duplas_marcadas(duplas, estados)

        self.assertEqual(selecionadas, [duplas[0], duplas[3]])


if __name__ == "__main__":
    unittest.main()
