from __future__ import annotations
from dataclasses import dataclass
from research_os.signals.models import SignalDirection, SignalResult

@dataclass(frozen=True)
class TelegramMessage:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()

class TelegramFormatter:
    def __init__(self, observation: bool = False):
        self.observation = observation

    def format(self, signal: SignalResult) -> TelegramMessage:
        if self.observation:
            return self._observation_message(signal)
        if signal.direction is SignalDirection.NONE:
            return TelegramMessage(
                f"⚪ {signal.symbol} NO SIGNAL\nReason: {signal.rationale[0] if signal.rationale else 'conditions not met'}"
            )
        icon="🟢" if signal.direction is SignalDirection.LONG else "🔴"
        s=signal.levels
        assert s is not None
        why="\n".join(f"• {x}" for x in signal.rationale if x) or "• validated directional evidence"
        risks="\n".join(f"• {x}" for x in signal.risks if x) or "• market conditions can change"
        probability_label = "Calibrated TP1 success estimate" if signal.probability_is_calibrated else "Research score (uncalibrated)"
        return TelegramMessage(
            f"{icon} {signal.symbol} {signal.direction.value.upper()}\n\n"
            f"{probability_label}: {signal.probability:.0%}\nLeverage: {signal.leverage:g}x\n\n"
            f"Entry: {s.entry_min:.2f}–{s.entry_max:.2f}\nSL: {s.stop_loss:.2f}\n"
            f"TP1: {s.tp1:.2f}\nTP2: {s.tp2:.2f}\nTP3: {s.tp3:.2f}\n\n"
            f"R:R: 1:{s.rr_tp1:.2f}\nHypothetical EV (R): {signal.expected_value:.3f}\n\n"
            f"Why:\n{why}\n\nRisk:\n{risks}",
            buttons=(("✅ Согласиться", f"confirm:{signal.signal_id}"),
                     ("❌ Отмена", f"cancel:{signal.signal_id}")),
        )

    def _observation_message(self, signal: SignalResult) -> TelegramMessage:
        if signal.direction is SignalDirection.NONE:
            return TelegramMessage(f"⚪ {signal.symbol}: условий для сигнала нет")
        levels = signal.levels
        assert levels is not None
        reasons = tuple(dict.fromkeys(self._comment(reason) for reason in signal.rationale if reason))
        comment = "\n".join(f"• {reason}" for reason in reasons[:8]) or "• Направленные аргументы отсутствуют"
        score = ("Оценка достижения TP1 по калиброванной модели" if signal.probability_is_calibrated
                 else "Исследовательский балл — не вероятность успеха")
        icon = "🟢" if signal.direction is SignalDirection.LONG else "🔴"
        return TelegramMessage(
            f"{icon} {signal.symbol} {signal.direction.value.upper()}\n"
            f"🔬 Наблюдение: качество сигналов проверяется\n"
            f"Время UTC: {signal.timestamp.isoformat()}\n\n"
            f"{score}: {signal.probability:.0%}\n"
            f"Вход: {levels.entry_min:.2f}–{levels.entry_max:.2f}\n"
            f"SL: {levels.stop_loss:.2f}\n"
            f"TP1: {levels.tp1:.2f} · TP2: {levels.tp2:.2f} · TP3: {levels.tp3:.2f}\n"
            f"R:R до TP1: 1:{levels.rr_tp1:.2f}\n\n"
            f"Комментарий системы:\n{comment}\n\n"
            "Риски: структура рынка может измениться до входа; гэпы и funding не учтены.\n"
            f"Расчётный EV: {signal.expected_value:.3f} R — модельная оценка, не подтверждённая доходность.\n"
            "Система сохраняет прогноз и отслеживает результат. Сделку открывает только человек."
        )

    @staticmethod
    def _comment(reason: str) -> str:
        translations = {
            "positive/negative short-term return": "Движение цены за последнюю минуту поддерживает направление",
            "positive/negative multi-bar return": "Движение цены за последние пять минут поддерживает направление",
            "bid depth exceeds ask depth": "Объём заявок на покупку превышает объём заявок на продажу",
            "ask depth exceeds bid depth": "Объём заявок на продажу превышает объём заявок на покупку",
            "aggressive buy volume exceeds sell volume": "Агрессивные покупки преобладают над продажами",
            "aggressive sell volume exceeds buy volume": "Агрессивные продажи преобладают над покупками",
            "price and cumulative delta moved in opposite directions": "Цена и накопленная дельта расходятся; это аргумент анализа",
        }
        for timeframe, label in (("15m", "15 минут"), ("1h", "час"), ("4h", "четыре часа"), ("1d", "сутки")):
            translations[f"{timeframe} directional context"] = f"Движение цены за {label} поддерживает направление"
        return translations.get(reason, reason)

    @staticmethod
    def callback_action(data: str) -> tuple[str, str]:
        action, sep, signal_id=data.partition(":")
        if not sep or action not in {"confirm", "cancel"} or not signal_id or len(signal_id) > 128:
            raise ValueError("invalid callback data")
        return action, signal_id
