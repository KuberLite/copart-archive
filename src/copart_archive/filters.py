"""Фильтры заказчика по строкам CSV. Ничего не отсеивается молча — всё в отчёте."""

from collections import Counter
from dataclasses import dataclass, field

from .config import Config
from .lotsearch import Lot


@dataclass
class FilterResult:
    passed: list[Lot] = field(default_factory=list)
    rejected: Counter[str] = field(default_factory=Counter)
    # отсеянные по повреждению / марке — чтобы видеть, не пора ли расширить списки
    other_damage: Counter[str] = field(default_factory=Counter)
    other_makes: Counter[str] = field(default_factory=Counter)

    def report(self) -> str:
        total = len(self.passed) + sum(self.rejected.values())
        lines = [f"Всего: {total}, прошло: {len(self.passed)}"]
        for reason, label in (("year", "году"), ("make", "марке"), ("damage", "повреждению")):
            lines.append(f"  отсеяно по {label}: {self.rejected[reason]}")
        if self.other_damage:
            lines.append("Повреждения вне групп (год и марка подошли):")
            lines += [f"  {n:4}  {v}" for v, n in self.other_damage.most_common()]
        if self.other_makes:
            lines.append("Марки вне списка (год подошёл):")
            lines += [f"  {n:4}  {v}" for v, n in self.other_makes.most_common()]
        return "\n".join(lines)


def reject_reason(lot: Lot, cfg: Config) -> str | None:
    if lot.year is None or lot.year < cfg.year_min:
        return "year"
    if lot.make not in cfg.makes:  # только точное совпадение: есть «HYUNDAI TRANSLEAD INC»
        return "make"
    if cfg.group_for(lot.primary_damage) is None:
        return "damage"
    return None


def apply(lots: list[Lot], cfg: Config) -> FilterResult:
    result = FilterResult()
    for lot in lots:
        reason = reject_reason(lot, cfg)
        if reason is None:
            result.passed.append(lot)
            continue
        result.rejected[reason] += 1
        if reason == "make":
            result.other_makes[lot.make] += 1
        elif reason == "damage":
            result.other_damage[lot.primary_damage] += 1
    return result
