from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, getcontext
from typing import Any, Mapping

getcontext().prec = 28


class DutchingValidationError(ValueError):
    """Erro de validacao do payload de dutching."""


@dataclass(frozen=True)
class Game:
    id: str
    mandante: str
    visitante: str
    odds: dict[str, Decimal]


@dataclass(frozen=True)
class Leg:
    game_id: str
    outcome: str
    odd: Decimal
    description: str


@dataclass(frozen=True)
class Ticket:
    id: str
    selections: dict[str, str]
    legs: tuple[Leg, ...]
    combined_odd: Decimal


@dataclass(frozen=True)
class Allocation:
    ticket: Ticket
    stake_units: int
    potential_return: Decimal


CENT = Decimal("0.01")


def calcular_dutching(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Calcula a distribuicao de banca para duplas combinadas.

    O payload deve seguir o formato descrito no README/exemplo. O retorno e um
    dicionario serializavel em JSON, com valores monetarios formatados como
    strings decimais para evitar perda de precisao.
    """

    bank = _decimal(payload.get("banca_total"), "banca_total")
    minimum_stake = _decimal(payload.get("minimo_por_bilhete"), "minimo_por_bilhete")
    increment = _decimal(payload.get("incremento_aposta", CENT), "incremento_aposta")
    fixed_lowest_odd_stake = _decimal(
        payload.get("valor_travado_menor_odd", Decimal("0")),
        "valor_travado_menor_odd",
    )
    fixed_highest_odd_stake = _decimal(
        payload.get("valor_travado_maior_odd", Decimal("0")),
        "valor_travado_maior_odd",
    )
    fixed_second_highest_odd_stake = _decimal(
        payload.get("valor_travado_segunda_maior_odd", Decimal("0")),
        "valor_travado_segunda_maior_odd",
    )

    _validate_positive_money(bank, "banca_total")
    _validate_positive_money(minimum_stake, "minimo_por_bilhete")
    _validate_positive_money(increment, "incremento_aposta")
    _validate_non_negative_money(fixed_lowest_odd_stake, "valor_travado_menor_odd")
    _validate_non_negative_money(fixed_highest_odd_stake, "valor_travado_maior_odd")
    _validate_non_negative_money(
        fixed_second_highest_odd_stake,
        "valor_travado_segunda_maior_odd",
    )
    _ensure_multiple(bank, increment, "banca_total")
    _ensure_multiple(minimum_stake, increment, "minimo_por_bilhete")
    _ensure_multiple(fixed_lowest_odd_stake, increment, "valor_travado_menor_odd")
    _ensure_multiple(fixed_highest_odd_stake, increment, "valor_travado_maior_odd")
    _ensure_multiple(
        fixed_second_highest_odd_stake,
        increment,
        "valor_travado_segunda_maior_odd",
    )

    games = _parse_games(payload.get("jogos"))
    tickets = _parse_tickets(payload.get("duplas_escolhidas"), games)
    fixed_ticket_requests = _parse_fixed_stake_requests(
        payload.get("apostas_travadas", []),
        tickets,
        increment,
    )
    result = _allocate(
        bank,
        minimum_stake,
        increment,
        tickets,
        fixed_lowest_odd_stake,
        fixed_highest_odd_stake,
        fixed_second_highest_odd_stake,
        fixed_ticket_requests,
    )
    return _serialize_result(bank, minimum_stake, increment, result)


def _parse_games(raw_games: Any) -> dict[str, Game]:
    if not isinstance(raw_games, list) or not raw_games:
        raise DutchingValidationError("'jogos' deve ser uma lista nao vazia.")

    games: dict[str, Game] = {}
    for index, raw_game in enumerate(raw_games, start=1):
        if not isinstance(raw_game, Mapping):
            raise DutchingValidationError(f"jogos[{index}] deve ser um objeto.")

        game_id = _required_str(raw_game, "id", f"jogos[{index}]")
        if game_id in games:
            raise DutchingValidationError(f"Jogo duplicado: '{game_id}'.")

        raw_odds = raw_game.get("odds")
        if not isinstance(raw_odds, Mapping) or not raw_odds:
            raise DutchingValidationError(f"jogos[{index}].odds deve ser um objeto nao vazio.")

        odds: dict[str, Decimal] = {}
        for outcome, odd_value in raw_odds.items():
            outcome_key = str(outcome)
            odd = _decimal(odd_value, f"jogos[{index}].odds.{outcome_key}")
            if odd <= Decimal("1"):
                raise DutchingValidationError(
                    f"Odd invalida em {game_id}/{outcome_key}: deve ser maior que 1."
                )
            odds[outcome_key] = odd

        games[game_id] = Game(
            id=game_id,
            mandante=str(raw_game.get("mandante", "")),
            visitante=str(raw_game.get("visitante", "")),
            odds=odds,
        )

    return games


def _parse_tickets(raw_tickets: Any, games: Mapping[str, Game]) -> list[Ticket]:
    if not isinstance(raw_tickets, list) or not raw_tickets:
        raise DutchingValidationError("'duplas_escolhidas' deve ser uma lista nao vazia.")

    tickets: list[Ticket] = []
    for index, raw_ticket in enumerate(raw_tickets, start=1):
        if not isinstance(raw_ticket, Mapping) or not raw_ticket:
            raise DutchingValidationError(f"duplas_escolhidas[{index}] deve ser um objeto.")

        selections = {str(game_id): str(outcome) for game_id, outcome in raw_ticket.items()}
        if len(selections) != 2:
            raise DutchingValidationError(
                f"duplas_escolhidas[{index}] deve conter exatamente 2 selecoes."
            )

        legs: list[Leg] = []
        combined_odd = Decimal("1")
        for game_id, outcome in selections.items():
            game = games.get(game_id)
            if game is None:
                raise DutchingValidationError(
                    f"duplas_escolhidas[{index}] referencia jogo inexistente: '{game_id}'."
                )
            if outcome not in game.odds:
                raise DutchingValidationError(
                    f"Resultado '{outcome}' nao existe nas odds do jogo '{game_id}'."
                )

            odd = game.odds[outcome]
            combined_odd *= odd
            legs.append(
                Leg(
                    game_id=game_id,
                    outcome=outcome,
                    odd=odd,
                    description=_describe_leg(game, outcome),
                )
            )

        tickets.append(
            Ticket(
                id=f"dupla_{index}",
                selections=selections,
                legs=tuple(legs),
                combined_odd=combined_odd,
            )
        )

    return tickets


def _parse_fixed_stake_requests(
    raw_fixed_stakes: Any,
    tickets: list[Ticket],
    increment: Decimal,
) -> list[tuple[Ticket, Decimal, str]]:
    if raw_fixed_stakes in (None, []):
        return []
    if not isinstance(raw_fixed_stakes, list):
        raise DutchingValidationError("'apostas_travadas' deve ser uma lista.")

    tickets_by_selection = {
        _selection_key(ticket.selections): ticket
        for ticket in tickets
    }
    seen_selections: set[tuple[tuple[str, str], ...]] = set()
    requests: list[tuple[Ticket, Decimal, str]] = []

    for index, raw_fixed_stake in enumerate(raw_fixed_stakes, start=1):
        if not isinstance(raw_fixed_stake, Mapping):
            raise DutchingValidationError(f"apostas_travadas[{index}] deve ser um objeto.")

        raw_selections = raw_fixed_stake.get("selecoes")
        if not isinstance(raw_selections, Mapping) or not raw_selections:
            raise DutchingValidationError(
                f"apostas_travadas[{index}].selecoes deve ser um objeto nao vazio."
            )

        selection_key = _selection_key(
            {str(game_id): str(outcome) for game_id, outcome in raw_selections.items()}
        )
        ticket = tickets_by_selection.get(selection_key)
        if ticket is None:
            raise DutchingValidationError(
                f"apostas_travadas[{index}] referencia dupla nao selecionada."
            )
        if selection_key in seen_selections:
            raise DutchingValidationError(
                f"apostas_travadas[{index}] duplica uma dupla ja travada."
            )

        amount = _decimal(raw_fixed_stake.get("valor"), f"apostas_travadas[{index}].valor")
        _validate_non_negative_money(amount, f"apostas_travadas[{index}].valor")
        _ensure_multiple(amount, increment, f"apostas_travadas[{index}].valor")
        if amount <= 0:
            continue

        seen_selections.add(selection_key)
        label = str(raw_fixed_stake.get("rotulo", f"aposta travada {index}"))
        requests.append((ticket, amount, label))

    return requests


def _allocate(
    bank: Decimal,
    minimum_stake: Decimal,
    increment: Decimal,
    tickets: list[Ticket],
    fixed_lowest_odd_stake: Decimal = Decimal("0"),
    fixed_highest_odd_stake: Decimal = Decimal("0"),
    fixed_second_highest_odd_stake: Decimal = Decimal("0"),
    fixed_ticket_requests: list[tuple[Ticket, Decimal, str]] | None = None,
) -> dict[str, Any]:
    active = sorted(tickets, key=lambda ticket: ticket.combined_odd)
    bank_units = _to_units_floor(bank, increment)
    minimum_units = _to_units_ceil(minimum_stake, increment)
    fixed_units_by_id: dict[str, int] = {}
    flexible = active.copy()

    explicit_label_keys = {
        _fixed_label_key(field_label)
        for _, _, field_label in fixed_ticket_requests or []
    }

    if (
        fixed_second_highest_odd_stake > 0
        and "segunda maior odd" not in explicit_label_keys
        and len(active) < 2
    ):
        return {
            "viavel": False,
            "allocations": [],
            "discarded": [],
            "alerts": [
                "Valor travado na segunda maior odd requer pelo menos dois bilhetes selecionados."
            ],
        }

    fixed_requests = list(fixed_ticket_requests or [])
    legacy_fixed_requests = [
        (active[0], fixed_lowest_odd_stake, "menor odd"),
        (active[-1], fixed_highest_odd_stake, "maior odd"),
    ]
    if fixed_second_highest_odd_stake > 0 and "segunda maior odd" not in explicit_label_keys:
        legacy_fixed_requests.append((active[-2], fixed_second_highest_odd_stake, "segunda maior odd"))

    for legacy_request in legacy_fixed_requests:
        if _fixed_label_key(legacy_request[2]) not in explicit_label_keys:
            fixed_requests.append(legacy_request)

    for ticket, amount, field_label in fixed_requests:
        fixed_error = _apply_fixed_stake(
            ticket=ticket,
            amount=amount,
            field_label=field_label,
            bank_units=bank_units,
            minimum_units=minimum_units,
            increment=increment,
            fixed_units_by_id=fixed_units_by_id,
            flexible=flexible,
        )
        if fixed_error is not None:
            return fixed_error

    required_minimum_units = len(flexible) * minimum_units + sum(fixed_units_by_id.values())

    if required_minimum_units > bank_units:
        minimum_total = required_minimum_units * increment
        return {
            "viavel": False,
            "allocations": [],
            "discarded": [],
            "alerts": [
                "Banca insuficiente para respeitar o minimo em todos os bilhetes "
                f"selecionados: minimo necessario {_money(minimum_total)}."
            ],
        }

    while flexible:
        fixed_units = sum(fixed_units_by_id.values())
        remaining_bank = (bank_units - fixed_units) * increment
        exact_stakes = _traditional_stakes(remaining_bank, flexible)
        under_minimum = [
            ticket
            for ticket in flexible
            if exact_stakes[ticket.id] < minimum_stake
        ]

        if not under_minimum:
            stake_units_by_id = dict(fixed_units_by_id)
            flexible_bank_units = bank_units - sum(fixed_units_by_id.values())
            stake_units_by_id.update(
                _round_traditional_stakes(
                    exact_stakes,
                    flexible,
                    flexible_bank_units,
                    increment,
                )
            )
            return _allocation_success(active, stake_units_by_id)

        ticket_to_fix = max(under_minimum, key=lambda ticket: ticket.combined_odd)
        fixed_units_by_id[ticket_to_fix.id] = minimum_units
        flexible.remove(ticket_to_fix)

    return _allocation_success(active, fixed_units_by_id)


def _selection_key(selections: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(game_id), str(outcome)) for game_id, outcome in selections.items()))


def _fixed_label_key(label: str) -> str:
    return label.strip().lower()


def _apply_fixed_stake(
    ticket: Ticket,
    amount: Decimal,
    field_label: str,
    bank_units: int,
    minimum_units: int,
    increment: Decimal,
    fixed_units_by_id: dict[str, int],
    flexible: list[Ticket],
) -> dict[str, Any] | None:
    if amount <= 0 or ticket.id in fixed_units_by_id:
        return None

    fixed_units = _to_units_floor(amount, increment)
    if fixed_units > bank_units:
        return {
            "viavel": False,
            "allocations": [],
            "discarded": [],
            "alerts": [f"Valor travado na {field_label} ultrapassa a banca total."],
        }
    if fixed_units < minimum_units:
        return {
            "viavel": False,
            "allocations": [],
            "discarded": [],
            "alerts": [
                f"Valor travado na {field_label} deve ser zero ou respeitar o minimo por bilhete."
            ],
        }

    fixed_units_by_id[ticket.id] = fixed_units
    if ticket in flexible:
        flexible.remove(ticket)
    return None


def _allocation_success(
    tickets: list[Ticket],
    stake_units_by_id: Mapping[str, int],
) -> dict[str, Any]:
    allocations = [
        Allocation(
            ticket=ticket,
            stake_units=stake_units_by_id[ticket.id],
            potential_return=Decimal("0"),
        )
        for ticket in tickets
    ]
    return {
        "viavel": True,
        "allocations": allocations,
        "discarded": [],
        "alerts": [],
        "coverage_required_units": sum(stake_units_by_id.values()),
    }


def _traditional_stakes(bank: Decimal, tickets: list[Ticket]) -> dict[str, Decimal]:
    probability_weights = {
        ticket.id: Decimal("1") / ticket.combined_odd
        for ticket in tickets
    }
    total_weight = sum(probability_weights.values(), Decimal("0"))
    return {
        ticket.id: bank * probability_weights[ticket.id] / total_weight
        for ticket in tickets
    }


def _round_traditional_stakes(
    exact_stakes: Mapping[str, Decimal],
    tickets: list[Ticket],
    bank_units: int,
    increment: Decimal,
) -> dict[str, int]:
    stake_units_by_id = {
        ticket.id: _to_units_floor(exact_stakes[ticket.id], increment)
        for ticket in tickets
    }
    remaining_units = bank_units - sum(stake_units_by_id.values())

    for _ in range(remaining_units):
        weakest_ticket = min(
            tickets,
            key=lambda ticket: (
                _ticket_return(ticket, stake_units_by_id, increment),
                ticket.combined_odd,
                ticket.id,
            ),
        )
        stake_units_by_id[weakest_ticket.id] += 1

    return stake_units_by_id


def _ticket_return(
    ticket: Ticket,
    stake_units_by_id: Mapping[str, int],
    increment: Decimal,
) -> Decimal:
    return _payout_value(stake_units_by_id[ticket.id] * increment * ticket.combined_odd)


def _serialize_result(
    bank: Decimal,
    minimum_stake: Decimal,
    increment: Decimal,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    allocations: list[Allocation] = result["allocations"]
    total_staked = sum((allocation.stake_units * increment for allocation in allocations), Decimal("0"))

    return {
        "viavel": result["viavel"],
        "banca_total": _money(bank),
        "minimo_por_bilhete": _money(minimum_stake),
        "incremento_aposta": _money(increment),
        "banca_alocada": _money(total_staked),
        "saldo_nao_alocado": _money(bank - total_staked),
        "cobertura_total": bool(allocations) and all(
            allocation.potential_return >= bank for allocation in allocations
        ),
        "banca_necessaria_cobertura": _money(
            result.get("coverage_required_units", 0) * increment
        ),
        "alertas": result["alerts"],
        "bilhetes": [_serialize_allocation(allocation, increment, bank) for allocation in allocations],
        "descartados": [_serialize_ticket(ticket) for ticket in result["discarded"]],
    }


def _serialize_allocation(allocation: Allocation, increment: Decimal, bank: Decimal) -> dict[str, Any]:
    stake = allocation.stake_units * increment
    potential_return = _payout_value(stake * allocation.ticket.combined_odd)
    return {
        **_serialize_ticket(allocation.ticket),
        "valor_apostado": _money(stake),
        "retorno_potencial": _money(potential_return),
        "lucro_sobre_banca": _money(potential_return - bank),
        "cobre_banca": potential_return >= bank,
    }


def _serialize_ticket(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "selecoes": ticket.selections,
        "pernas": [
            {
                "jogo_id": leg.game_id,
                "resultado": leg.outcome,
                "odd": _format_decimal(leg.odd, places=4),
                "descricao": leg.description,
            }
            for leg in ticket.legs
        ],
        "odd_combinada": _format_decimal(ticket.combined_odd, places=4),
    }


def _describe_leg(game: Game, outcome: str) -> str:
    if outcome == "1":
        return f"{game.mandante} vence"
    if outcome.upper() == "X":
        return f"{game.mandante} x {game.visitante} empata"
    if outcome == "2":
        return f"{game.visitante} vence"
    return f"{game.id}: {outcome}"


def _decimal(value: Any, field_name: str) -> Decimal:
    if value is None:
        raise DutchingValidationError(f"Campo obrigatorio ausente: '{field_name}'.")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise DutchingValidationError(f"Campo '{field_name}' deve ser numerico.") from exc


def _validate_positive_money(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise DutchingValidationError(f"Campo '{field_name}' deve ser maior que zero.")


def _validate_non_negative_money(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise DutchingValidationError(f"Campo '{field_name}' nao pode ser negativo.")


def _ensure_multiple(value: Decimal, increment: Decimal, field_name: str) -> None:
    units = value / increment
    if units != units.to_integral_value():
        raise DutchingValidationError(
            f"Campo '{field_name}' deve ser multiplo de {_money(increment)}."
        )


def _required_str(raw: Mapping[str, Any], key: str, scope: str) -> str:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        raise DutchingValidationError(f"{scope}.{key} e obrigatorio.")
    return str(value)


def _to_units_floor(value: Decimal, increment: Decimal) -> int:
    return int((value / increment).to_integral_value(rounding=ROUND_FLOOR))


def _to_units_ceil(value: Decimal, increment: Decimal) -> int:
    return int((value / increment).to_integral_value(rounding=ROUND_CEILING))


def _money(value: Decimal) -> str:
    return _format_decimal(value, places=2)


def _payout_value(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_FLOOR)


def _format_decimal(value: Decimal, places: int) -> str:
    quantizer = Decimal("1").scaleb(-places)
    return str(value.quantize(quantizer))
