# Betapp Dutching Backend

Backend em Python 3.10+ para calcular dutching de duplas combinadas sem scraping direto. O modulo recebe um payload JSON com odds simuladas de uma API externa, valida os dados e distribui a banca respeitando o valor minimo por bilhete.

## Como executar

```bash
python -m dutching.cli examples/payload_exemplo.json
```

## API Python

```python
from dutching import calcular_dutching

resultado = calcular_dutching(payload)
```

## Regra de calculo

1. Calcula a odd combinada de cada dupla multiplicando as odds das pernas.
2. Calcula o peso implicito de cada dupla como `P_i = 1 / odd_combinada`.
3. Soma os pesos selecionados em `S = sum(P_i)`.
4. Calcula a aposta teorica de cada dupla como `banca_total * P_i / S`.
5. Se alguma aposta teorica ficar abaixo do `minimo_por_bilhete`, trava essa dupla no minimo e subtrai esse valor da banca disponivel.
6. Recalcula o Dutching tradicional apenas para as duplas restantes usando o saldo que sobrou.
7. Converte as apostas para centavos e distribui centavos residuais no bilhete com menor retorno potencial atual.

Opcionalmente, o payload pode enviar `valor_travado_menor_odd` e/ou `valor_travado_maior_odd`. Quando um desses valores e maior que zero, a respectiva dupla extrema recebe exatamente esse valor e o Dutching e aplicado apenas nas demais duplas com a banca restante.

O retorno potencial e arredondado para baixo em centavos, deixando a validacao conservadora. Duplas travadas no minimo continuam aparecendo no resultado. Valores monetarios saem como strings decimais para preservar precisao em JSON.

## Testes

```bash
python -m unittest
```
