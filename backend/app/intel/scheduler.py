from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.core.config import load_yaml_config
from backend.app.core.db import SessionLocal
from backend.app.core.logging import logger
from backend.app.intel.pipeline import intel_enabled, run_intel_cycle


class IntelScheduler:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        cfg = load_yaml_config().get("intel") or {}
        interval = int(cfg.get("poll_interval_seconds", 900))
        self.scheduler.add_job(self.tick, "interval", seconds=interval, id="intel_tick", replace_existing=True)
        self.scheduler.start()
        self._running = True
        logger.info("intel scheduler started, interval=%ss", interval)

    def stop(self) -> None:
        if not self._running:
            return
        self.scheduler.shutdown(wait=False)
        self._running = False
        logger.info("intel scheduler stopped")

    def tick(self) -> None:
        # 非交易时段仍采集+预测；是否下单由 pipeline / 风控决定
        db = SessionLocal()
        try:
            if not intel_enabled(db):
                return
            run_intel_cycle(db, force=False)
        except Exception:  # noqa: BLE001
            logger.exception("intel tick failed")
        finally:
            db.close()


intel_scheduler = IntelScheduler()
