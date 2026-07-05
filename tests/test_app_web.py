from __future__ import annotations

import unittest

from app_web import (
    chave_dupla,
    filtrar_duplas_marcadas,
    gerar_duplas_possiveis,
    label_dupla,
    montar_payload_calculo,
)


def jogos_exemplo() -> list[dict]:
    return [
        {
            "id": "jogo_1",
            "mandante": "Brasil",
            "visitante": "Noruega",
            "odds": {"1": 1.80, "X": 3.70, "2": 4.50},
        },
        {
            "id": "jogo_2",
            "mandante": "México",
            "visitante": "Inglaterra",
            "odds": {"1": 3.10, "X": 3.20, "2": 2.40},
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

        label = label_dupla(duplas[2], jogos_por_id)

        self.assertEqual(
            label,
            "Brasil vence (1.80) + Inglaterra vence (2.40) | Odd combinada: 4.32",
        )

    def test_payload_envia_exatamente_duplas_marcadas(self) -> None:
        payload_base = {"jogos": jogos_exemplo()}
        duplas_marcadas = [
            {"jogo_1": "1", "jogo_2": "X"},
            {"jogo_1": "2", "jogo_2": "2"},
        ]

        payload = montar_payload_calculo(payload_base, 10.0, 0.5, duplas_marcadas, 2.0, 1.5)

        self.assertEqual(payload["duplas_escolhidas"], duplas_marcadas)
        self.assertEqual(payload["banca_total"], "10.00")
        self.assertEqual(payload["minimo_por_bilhete"], "0.50")
        self.assertEqual(payload["valor_travado_menor_odd"], "2.00")
        self.assertEqual(payload["valor_travado_maior_odd"], "1.50")

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
