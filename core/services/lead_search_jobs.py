"""Persisted lead searches for a single application worker.

Opaque run IDs are capability URLs. No cross-client listing endpoint is exposed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

from core.services.production_lead_pipeline import ProductionLeadPipeline


TERMINAL = {"completed", "partial", "cancelled", "failed", "interrupted"}


class SearchBusy(Exception):
    pass


class LeadSearchJobs:
    def __init__(self, path=None, *, pipeline_factory=ProductionLeadPipeline, concurrency=2):
        self.path = str(path or os.getenv('LEAD_SEARCH_DB_PATH', 'data/lead-searches.sqlite3'))
        self.pipeline_factory = pipeline_factory
        self.slots = asyncio.Semaphore(concurrency)
        self.tasks = {}
        self.started = False
        self.logger = logging.getLogger("agent.runtime")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self):
        if self.started:
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS searches (id TEXT PRIMARY KEY, request_key TEXT UNIQUE, request TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)")
            for row in db.execute("SELECT id, result FROM searches WHERE status NOT IN ('completed','partial','cancelled','failed','interrupted')").fetchall():
                result = json.loads(row["result"])
                result.setdefault("metadata", {}).update(stage="interrupted", stop_reason="server_restarted", completed=True)
                db.execute("UPDATE searches SET status='interrupted', result=?, updated=? WHERE id=?",
                           (json.dumps(result, ensure_ascii=False), time.time(), row["id"]))
        self.started = True

    def get(self, run_id):
        self.start()
        with self.connect() as db:
            row = db.execute("SELECT * FROM searches WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "status": row["status"], "request": json.loads(row["request"]),
                "result": json.loads(row["result"]), "created_at": row["created"], "updated_at": row["updated"]}

    def save(self, run_id, status, result):
        with self.connect() as db:
            db.execute("UPDATE searches SET status=?, result=?, updated=? WHERE id=?", (status, json.dumps(result, ensure_ascii=False), time.time(), run_id))

    async def create(self, request, request_key):
        self.start()
        with self.connect() as db:
            existing = db.execute("SELECT id, request FROM searches WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if json.loads(existing["request"]) != request:
                    raise ValueError("This request key belongs to a different search.")
                return self.get(existing["id"])
            active = db.execute("SELECT COUNT(*) FROM searches WHERE status NOT IN ('completed','partial','cancelled','failed','interrupted')").fetchone()[0]
            if active >= 10:
                raise SearchBusy("The search queue is full. Please try again shortly.")
            run_id = secrets.token_urlsafe(32)
            result = {"leads": [], "steps": [], "metadata": {"stage": "queued", "requested_count": request["target_count"], "shortfall": request["target_count"]}}
            db.execute("INSERT INTO searches VALUES (?,?,?,?,?,?,?)", (run_id, request_key, json.dumps(request), "queued", json.dumps(result), time.time(), time.time()))
        task = asyncio.create_task(self.work(run_id, request))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))
        return self.get(run_id)

    async def work(self, run_id, request):
        async def progress(result):
            self.save(run_id, result.get("metadata", {}).get("stage", "running"), result)
        try:
            async with self.slots:
                self.logger.info("lead_search_job_started run_id=%s", run_id)
                arguments = dict(request)
                mode = arguments.pop('mode', 'generic')
                if mode == 'velit' and self.pipeline_factory is ProductionLeadPipeline:
                    from core.services.velit.velit_lead_pipeline import VelitLeadPipeline
                    pipeline = VelitLeadPipeline()
                else:
                    pipeline = self.pipeline_factory()
                result = await pipeline.run(**arguments, on_progress=progress)
                self.save(run_id, result["metadata"]["stage"], result)
                self.logger.info("lead_search_job_finished run_id=%s stage=%s returned=%s", run_id,
                                 result["metadata"]["stage"], len(result.get("leads", [])))
        except asyncio.CancelledError:
            row = self.get(run_id)
            if row and row["status"] not in TERMINAL:
                result = row["result"]
                result.setdefault("metadata", {}).update(stage="cancelled", stop_reason="cancelled", completed=True)
                self.save(run_id, "cancelled", result)
        except Exception as exc:
            self.logger.error("lead_search_job_failed run_id=%s error_type=%s", run_id, type(exc).__name__)
            row = self.get(run_id)
            if row:
                result = row["result"]
                result.setdefault("metadata", {}).update(stage="failed", stop_reason="internal_error", completed=True,
                    warnings=["Search could not finish. Any results already found are preserved. Please retry."])
                self.save(run_id, "failed", result)

    async def cancel(self, run_id):
        row = self.get(run_id)
        if not row or row["status"] in TERMINAL:
            return row
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        row = self.get(run_id)
        if row["status"] not in TERMINAL:
            row["result"].setdefault("metadata", {}).update(stage="cancelled", stop_reason="cancelled", completed=True)
            self.save(run_id, "cancelled", row["result"])
        return self.get(run_id)

    async def close(self):
        active = list(self.tasks.items())
        for _, task in active:
            task.cancel()
        await asyncio.gather(*(task for _, task in active), return_exceptions=True)
        for run_id, _ in active:
            row = self.get(run_id)
            if row and row["status"] == "cancelled":
                row["result"].setdefault("metadata", {}).update(stage="interrupted", stop_reason="server_restarted")
                self.save(run_id, "interrupted", row["result"])
        self.started = False
