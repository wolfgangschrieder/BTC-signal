from __future__ import annotations
from dataclasses import dataclass
from research_os.signals.models import SignalDirection, SignalResult

@dataclass(frozen=True)
class TelegramMessage:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()

class TelegramFormatter:
    def format(self, signal: SignalResult) -> TelegramMessage:
        if signal.direction is SignalDirection.NONE:
            return TelegramMessage(
                f"⚪ {signal.symbol} NO SIGNAL\nReason: {signal.rationale[0] if signal.rationale else 'conditions not met'}"
            )
        icon="🟢" if signal.direction is SignalDirection.LONG else "🔴"
        s=signal.levels
        assert s is not None
        why="\n".join(f"• {x}" for x in signal.rationale if x) or "• validated directional evidence"
        risks="\n".join(f"• {x}" for x in signal.risks if x) or "• market conditions can change"
        return TelegramMessage(
            f"{icon} {signal.symbol} {signal.direction.value.upper()}\n\n"
            f"Probability: {signal.probability:.0%}\nLeverage: {signal.leverage:g}x\n\n"
            f"Entry: {s.entry_min:.2f}–{s.entry_max:.2f}\nSL: {s.stop_loss:.2f}\n"
            f"TP1: {s.tp1:.2f}\nTP2: {s.tp2:.2f}\nTP3: {s.tp3:.2f}\n\n"
            f"R:R: 1:{s.rr_tp1:.2f}\nEV: {signal.expected_value:.3f}\n\n"
            f"Why:\n{why}\n\nRisk:\n{risks}",
            buttons=(("✅ Согласиться", f"confirm:{signal.signal_id}"),
                     ("❌ Отмена", f"cancel:{signal.signal_id}")),
        )

    @staticmethod
    def callback_action(data: str) -> tuple[str, str]:
        action, sep, signal_id=data.partition(":")
        if not sep or action not in {"confirm", "cancel"} or not signal_id or len(signal_id) > 128:
            raise ValueError("invalid callback data")
        return action, signal_id
