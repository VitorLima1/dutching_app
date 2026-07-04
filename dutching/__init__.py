"""Backend de dutching para apostas combinadas."""

from .calculator import DutchingValidationError, calcular_dutching

__all__ = ["DutchingValidationError", "calcular_dutching"]
