"""ИИ-прогноз времени прибытия транспорта (онлайн-табло ETA).

По аналогии с городскими проектами «умных остановок» (GPS-телеметрия
транспорта → ИИ-модель → электронное табло на остановке, как Urban Way
в Бельцах): каждый пункт доставки сети — магазин, принимающий машины
поставщиков/РЦ, или адрес покупателя, ждущий курьера, — получает
онлайн-табло с прогнозом времени прибытия.

Модель — онлайн-обучение без внешних зависимостей и без фоновых
потоков (в духе evolve-on-poll):

* для каждого класса транспорта (``truck`` — грузовики РЦ,
  ``courier`` — курьеры доставки) ведётся экспоненциально взвешенная
  оценка фактической скорости (EWMA) и её дисперсии; модель дообучается
  на каждом завершённом плече маршрута — «телеметрия рейса» это пара
  (метры по дорожному графу, фактические секунды);
* трафик по часу суток учитывается обучаемым коэффициентом на каждый
  час (часы пик системно медленнее — модель это выучивает сама);
* длительности без дистанции (вручение заказа) прогнозируются той же
  схемой EWMA по классу события;
* прогноз: остаток пути по дорожному графу / прогнозная скорость часа,
  неопределённость ±1σ из выученной дисперсии.

API::

    p = get_predictor()
    p.observe("truck", road_m=1850, seconds=48, hour=18)   # обучение
    eta_s, sigma_s, n = p.predict("truck", remaining_m=700, hour=18)
    p.observe_duration("handover", seconds=22)
    dur_s, sigma_s, n = p.predict_duration("handover")
"""

import math
import threading
from typing import Dict, Optional, Tuple

#: скорость обучения EWMA: свежие рейсы весят больше старых
_ALPHA = 0.25

#: априорные скорости до первых наблюдений, м/с (эмуляция ускорена)
#: ``tanker`` — бензовоз топливного контура (нефтебаза → АЗС по трассам
#: Молдовы, `webapp/peco_fuel.py`): межгородские плечи там на порядок
#: длиннее городских (Кишинёв→Бэлць ≈ 134 км), а контур, как и все
#: прочие, — evolve-on-poll без фонового потока, опрашивается раз в
#: доли секунды. Чтобы рейс оставался наблюдаемым за один короткий
#: прогон (а не отрисовывался одним прыжком), константу подобрали так,
#: чтобы самое длинное плечо сети занимало порядка минуты ускоренного
#: времени: 134 300 м / 2200 м/с ≈ 61 с — то же соотношение «реальная
#: трасса, но сжатое до минуты», что уже применено к truck и courier.
_PRIOR_SPEED = {"truck": 45.0, "courier": 22.0, "tanker": 2200.0}
_PRIOR_DURATION = {"handover": 25.0}


class _Ewma:
    """Экспоненциально взвешенные среднее и дисперсия (West, 1979)."""

    def __init__(self, prior: float):
        self.mean = prior
        self.var = (prior * 0.25) ** 2
        self.n = 0

    def update(self, x: float) -> None:
        d = x - self.mean
        self.mean += _ALPHA * d
        self.var = (1 - _ALPHA) * (self.var + _ALPHA * d * d)
        self.n += 1

    @property
    def sigma(self) -> float:
        return math.sqrt(max(self.var, 0.0))


class EtaPredictor:
    """Онлайн-обучаемый прогнозист прибытия для табло пунктов доставки."""

    def __init__(self):
        self._lock = threading.Lock()
        self._speed: Dict[str, _Ewma] = {
            k: _Ewma(v) for k, v in _PRIOR_SPEED.items()}
        self._duration: Dict[str, _Ewma] = {
            k: _Ewma(v) for k, v in _PRIOR_DURATION.items()}
        # коэффициент трафика конкретного часа: v_час / v_средняя
        self._hour_factor: Dict[Tuple[str, int], _Ewma] = {}

    # ----- обучение (телеметрия завершённых плеч) -----------------------
    def observe(self, kind: str, road_m: float, seconds: float,
                hour: Optional[int] = None) -> None:
        if seconds <= 0 or road_m <= 0:
            return
        v = road_m / seconds
        with self._lock:
            sp = self._speed.setdefault(kind, _Ewma(v))
            sp.update(v)
            if hour is not None and sp.mean > 0:
                hf = self._hour_factor.setdefault(
                    (kind, int(hour) % 24), _Ewma(1.0))
                hf.update(v / sp.mean)

    def observe_duration(self, kind: str, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            self._duration.setdefault(kind, _Ewma(seconds)).update(seconds)

    # ----- прогноз ------------------------------------------------------
    def predict(self, kind: str, remaining_m: float,
                hour: Optional[int] = None) -> Tuple[float, float, int]:
        """Прогноз (секунды, ±σ секунд, наблюдений в модели)."""
        with self._lock:
            sp = self._speed.get(kind) or _Ewma(_PRIOR_SPEED.get(kind, 20.0))
            factor = 1.0
            if hour is not None:
                hf = self._hour_factor.get((kind, int(hour) % 24))
                if hf is not None and hf.n > 0:
                    factor = max(0.4, min(1.6, hf.mean))
            v = max(1.0, sp.mean * factor)
            eta = max(0.0, remaining_m) / v
            # относительная неопределённость скорости → секунды
            rel = sp.sigma / sp.mean if sp.mean > 0 else 0.3
            sigma = eta * max(0.05, min(0.6, rel))
            return eta, sigma, sp.n

    def predict_duration(self, kind: str) -> Tuple[float, float, int]:
        with self._lock:
            d = self._duration.get(kind) or _Ewma(
                _PRIOR_DURATION.get(kind, 20.0))
            return d.mean, d.sigma, d.n

    # ----- сводка модели (для табло и документации) ---------------------
    def summary(self) -> dict:
        with self._lock:
            return {
                "speeds": {k: {"mps": round(e.mean, 2),
                               "sigma": round(e.sigma, 2), "obs": e.n}
                           for k, e in self._speed.items()},
                "durations": {k: {"sec": round(e.mean, 1),
                                  "sigma": round(e.sigma, 1), "obs": e.n}
                              for k, e in self._duration.items()},
                "hour_factors": {
                    f"{k}@{h:02d}": round(e.mean, 3)
                    for (k, h), e in sorted(self._hour_factor.items())
                    if e.n > 0},
            }


_predictor: Optional[EtaPredictor] = None
_plock = threading.Lock()


def get_predictor() -> EtaPredictor:
    """Единый прогнозист процесса: РЦ и доставка учат одну модель."""
    global _predictor
    with _plock:
        if _predictor is None:
            _predictor = EtaPredictor()
        return _predictor
