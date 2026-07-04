from __future__ import annotations

import unittest
from decimal import Decimal

from dutching import calcular_dutching
from dutching.calculator import DutchingValidationError


def payload_exemplo() -> dict:
    return {
        "banca_total": 10.00,
        "minimo_por_bilhete": 0.50,
        "jogos": [
            {
                "id": "jogo_1",
                "mandante": "Canada",
                "visitante": "Marrocos",
                "odds": {"1": 5.50, "X": 3.50, "2": 1.72},
            },
            {
                "id": "jogo_2",
                "mandante": "Paraguai",
                "visitante": "Franca",
                "odds": {"1": 17.00, "X": 7.00, "2": 1.16},
            },
        ],
        "duplas_escolhidas": [
            {"jogo_1": "2", "jogo_2": "2"},
            {"jogo_1": "X", "jogo_2": "2"},
            {"jogo_1": "1", "jogo_2": "2"},
            {"jogo_1": "2", "jogo_2": "1"},
        ],
    }


def payload_nove_duplas() -> dict:
    payload = payload_exemplo()
    payload["duplas_escolhidas"] = [
        {"jogo_1": "1", "jogo_2": "1"},
        {"jogo_1": "1", "jogo_2": "X"},
        {"jogo_1": "1", "jogo_2": "2"},
        {"jogo_1": "X", "jogo_2": "1"},
        {"jogo_1": "X", "jogo_2": "X"},
        {"jogo_1": "X", "jogo_2": "2"},
        {"jogo_1": "2", "jogo_2": "1"},
        {"jogo_1": "2", "jogo_2": "X"},
        {"jogo_1": "2", "jogo_2": "2"},
    ]
    return payload


class DutchingCalculatorTest(unittest.TestCase):
    def test_trava_dupla_abaixo_do_minimo_sem_descartar(self) -> None:
        result = calcular_dutching(payload_exemplo())

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "10.00")
        self.assertEqual(result["saldo_nao_alocado"], "0.00")
        self.assertEqual(result["descartados"], [])
        self.assertEqual(result["alertas"], [])
        self.assertEqual(len(result["bilhetes"]), 4)

        for ticket in result["bilhetes"]:
            self.assertGreater(Decimal(ticket["valor_apostado"]), Decimal("0.49"))

        zebra = next(ticket for ticket in result["bilhetes"] if ticket["id"] == "dupla_4")
        self.assertEqual(zebra["valor_apostado"], "0.50")
        self.assertGreater(Decimal(zebra["retorno_potencial"]), Decimal("10.00"))

    def test_dutching_tradicional_recalcula_saldo_apos_fixar_minimos(self) -> None:
        result = calcular_dutching(payload_exemplo())

        returns = [
            Decimal(ticket["retorno_potencial"])
            for ticket in result["bilhetes"]
            if ticket["id"] != "dupla_4"
        ]
        self.assertLessEqual(max(returns) - min(returns), Decimal("0.06"))

    def test_mantem_duplas_no_minimo_com_banca_menor(self) -> None:
        payload = payload_exemplo()
        payload["banca_total"] = 5.00

        result = calcular_dutching(payload)

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "5.00")
        self.assertEqual(result["descartados"], [])
        self.assertEqual(result["alertas"], [])
        self.assertEqual(len(result["bilhetes"]), 4)

        zebra = next(ticket for ticket in result["bilhetes"] if ticket["id"] == "dupla_4")
        self.assertEqual(zebra["valor_apostado"], "0.50")

        returns = [
            Decimal(ticket["retorno_potencial"])
            for ticket in result["bilhetes"]
            if ticket["id"] != "dupla_4"
        ]
        self.assertLessEqual(max(returns) - min(returns), Decimal("0.05"))

    def test_nove_duplas_mantem_todas_e_fixa_zebras_no_minimo(self) -> None:
        result = calcular_dutching(payload_nove_duplas())

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "10.00")
        self.assertEqual(result["descartados"], [])
        self.assertEqual(result["alertas"], [])
        self.assertEqual(len(result["bilhetes"]), 9)

        fixed_tickets = [
            ticket for ticket in result["bilhetes"] if Decimal(ticket["valor_apostado"]) == Decimal("0.50")
        ]
        self.assertEqual(
            [ticket["id"] for ticket in fixed_tickets],
            ["dupla_5", "dupla_7", "dupla_2", "dupla_4", "dupla_1"],
        )

        returns = [
            Decimal(ticket["retorno_potencial"])
            for ticket in result["bilhetes"]
            if Decimal(ticket["valor_apostado"]) > Decimal("0.50")
        ]
        self.assertLessEqual(max(returns) - min(returns), Decimal("0.05"))

    def test_banca_alta_permite_mais_duplas_no_dutching_tradicional(self) -> None:
        payload = payload_nove_duplas()
        payload["banca_total"] = 1000.00

        result = calcular_dutching(payload)

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "1000.00")
        self.assertEqual(result["descartados"], [])
        self.assertEqual(result["alertas"], [])
        self.assertEqual(len(result["bilhetes"]), 9)

        returns = [Decimal(ticket["retorno_potencial"]) for ticket in result["bilhetes"]]
        self.assertLessEqual(max(returns) - min(returns), Decimal("0.60"))

    def test_valor_travado_na_menor_odd_isola_favorito_e_dutcha_restante(self) -> None:
        payload = payload_exemplo()
        payload["valor_travado_menor_odd"] = "2.00"

        result = calcular_dutching(payload)

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "10.00")
        self.assertEqual(result["descartados"], [])
        favorito = result["bilhetes"][0]
        self.assertEqual(favorito["id"], "dupla_1")
        self.assertEqual(favorito["valor_apostado"], "2.00")

        demais_retornos = [
            Decimal(ticket["retorno_potencial"])
            for ticket in result["bilhetes"][1:]
        ]
        self.assertLessEqual(max(demais_retornos) - min(demais_retornos), Decimal("0.15"))

    def test_valores_travados_menor_e_maior_odd_isolam_extremos(self) -> None:
        payload = payload_exemplo()
        payload["valor_travado_menor_odd"] = "2.00"
        payload["valor_travado_maior_odd"] = "1.50"

        result = calcular_dutching(payload)

        self.assertTrue(result["viavel"])
        self.assertEqual(result["banca_alocada"], "10.00")
        self.assertEqual(result["alertas"], [])

        menor_odd = result["bilhetes"][0]
        maior_odd = result["bilhetes"][-1]
        self.assertEqual(menor_odd["id"], "dupla_1")
        self.assertEqual(menor_odd["valor_apostado"], "2.00")
        self.assertEqual(maior_odd["id"], "dupla_4")
        self.assertEqual(maior_odd["valor_apostado"], "1.50")

        meio_retornos = [
            Decimal(ticket["retorno_potencial"])
            for ticket in result["bilhetes"][1:-1]
        ]
        self.assertLessEqual(max(meio_retornos) - min(meio_retornos), Decimal("0.05"))

    def test_inviavel_somente_quando_minimo_total_ultrapassa_banca(self) -> None:
        payload = payload_exemplo()
        payload["banca_total"] = 1.50

        result = calcular_dutching(payload)

        self.assertFalse(result["viavel"])
        self.assertEqual(result["bilhetes"], [])
        self.assertEqual(result["descartados"], [])
        self.assertTrue(result["alertas"])

    def test_rejeita_resultado_inexistente(self) -> None:
        payload = payload_exemplo()
        payload["duplas_escolhidas"][0] = {"jogo_1": "9", "jogo_2": "2"}

        with self.assertRaises(DutchingValidationError):
            calcular_dutching(payload)


if __name__ == "__main__":
    unittest.main()
