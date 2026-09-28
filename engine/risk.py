"""RiskManager: validates every order before execution."""
from typing import List

from .models import Order, OrderStatus


class RiskManager:
    def __init__(self, max_exposure: float = 100_000.0, max_position: int = 100):
        self.max_exposure = max_exposure
        self.max_position = max_position
        self.rejected: List[Order] = []

    def validate(self, order: Order, current_position: int, cash: float | None = None) -> bool:
        """Reject if order value exceeds max exposure, position cap, or available cash.

        cash=None skips the cash check (backward compat). Only BUY orders are
        cash-constrained — selling frees cash.
        """
        order_value = order.price * order.volume

        if cash is not None and order.side.value == "BUY" and order_value > cash:
            order.status = OrderStatus.REJECTED
            order.reason = f"order value {order_value:.2f} > cash {cash:.2f}"
            self.rejected.append(order)
            return False

        if order_value > self.max_exposure:
            order.status = OrderStatus.REJECTED
            order.reason = f"order value {order_value:.2f} > max exposure {self.max_exposure:.2f}"
            self.rejected.append(order)
            return False

        if order.side.value == "BUY" and current_position + order.volume > self.max_position:
            order.status = OrderStatus.REJECTED
            order.reason = f"position {current_position} + {order.volume} > max {self.max_position}"
            self.rejected.append(order)
            return False

        order.status = OrderStatus.FILLED
        return True
