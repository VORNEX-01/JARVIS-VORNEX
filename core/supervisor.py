"""
VORNEX Supervisor — persistent health/awareness loop.

Observes the running assistant and emits structured health events.
It does not execute arbitrary actions or modify code.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SupervisorState:
    started_at: float = field(default_factory=time.monotonic)
    last_tick: float = 0.0
    last_health_check: float = 0.0
    ticks: int = 0
    failures: int = 0
    last_error: str = ""
    session_alive: bool = False
    awake: bool = False
    speaking: bool = False
    last_user_speech: float = 0.0
    last_audio_rx: float = 0.0
    last_audio_tx: float = 0.0
    last_model_rx: float = 0.0
    reconnects: int = 0
    tool_failures: int = 0
    cpu: float | None = None
    ram: float | None = None
    temp: float | None = None
    gpu: float | None = None


class Supervisor:
    def __init__(
        self,
        *,
        check_fn: Callable[[], dict],
        event_fn: Callable[[dict], None],
        event_bus=None,
        interval: float = 5.0,
        health_interval: float = 15.0,
    ):
        self.check_fn = check_fn
        self.event_fn = event_fn
        self.event_bus = event_bus
        self.interval = max(1.0, float(interval))
        self.health_interval = max(self.interval, float(health_interval))

        self.state = SupervisorState()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._last_alert: dict[str, float] = {}

    def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._stop.clear()
        self._task = asyncio.create_task(
            self._run(),
            name="vornex-supervisor",
        )

    async def stop(self) -> None:
        self._stop.set()

        task = self._task
        self._task = None

        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass

    def snapshot(self) -> dict:
        s = self.state

        return {
            "uptime": round(time.monotonic() - s.started_at, 1),
            "ticks": s.ticks,
            "failures": s.failures,
            "last_error": s.last_error,
            "session_alive": s.session_alive,
            "awake": s.awake,
            "speaking": s.speaking,
            "last_user_speech": s.last_user_speech,
            "last_audio_rx": s.last_audio_rx,
            "last_audio_tx": s.last_audio_tx,
            "last_model_rx": s.last_model_rx,
            "reconnects": s.reconnects,
            "tool_failures": s.tool_failures,
            "cpu": s.cpu,
            "ram": s.ram,
            "temp": s.temp,
            "gpu": s.gpu,
        }

    def _emit(self, kind: str, **data) -> None:
        now = time.monotonic()
        last = self._last_alert.get(kind, 0.0)

        if now - last < 60.0:
            return

        self._last_alert[kind] = now

        event = {
            "source": "supervisor",
            "kind": kind,
            "ts": time.time(),
            **data,
        }

        try:
            self.event_fn(event)
        except Exception:
            traceback.print_exc()

        if self.event_bus is not None:
            try:
                self.event_bus.emit(kind, **data)
            except Exception:
                traceback.print_exc()

    async def _run(self) -> None:
        self.state.started_at = time.monotonic()

        while not self._stop.is_set():
            self.state.last_tick = time.monotonic()
            self.state.ticks += 1

            try:
                now = time.monotonic()

                if now - self.state.last_health_check >= self.health_interval:
                    self.state.last_health_check = now

                    try:
                        data = await asyncio.to_thread(self.check_fn)

                        if isinstance(data, dict):
                            self.state.cpu = data.get("cpu")
                            self.state.ram = data.get("ram")
                            self.state.temp = data.get("temp")
                            self.state.gpu = data.get("gpu")

                            if self.state.cpu is not None and self.state.cpu >= 95:
                                self._emit(
                                    "resource_warning",
                                    resource="cpu",
                                    value=self.state.cpu,
                                )

                            if self.state.ram is not None and self.state.ram >= 95:
                                self._emit(
                                    "resource_warning",
                                    resource="ram",
                                    value=self.state.ram,
                                )

                            if self.state.temp is not None and self.state.temp >= 90:
                                self._emit(
                                    "resource_warning",
                                    resource="temperature",
                                    value=self.state.temp,
                                )

                            if self.state.gpu is not None and self.state.gpu >= 98:
                                self._emit(
                                    "resource_warning",
                                    resource="gpu",
                                    value=self.state.gpu,
                                )

                    except Exception as exc:
                        self.state.failures += 1
                        self.state.last_error = str(exc)

                        self._emit(
                            "health_check_failed",
                            error=str(exc),
                        )

            except Exception as exc:
                self.state.failures += 1
                self.state.last_error = str(exc)

                self._emit(
                    "supervisor_error",
                    error=str(exc),
                )

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.interval,
                )
            except asyncio.TimeoutError:
                pass
