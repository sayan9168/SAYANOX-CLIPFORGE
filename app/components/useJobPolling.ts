"use client";
import { useEffect, useRef, useState } from "react";
import { ApiError, requestJson } from "../../lib/api";
import { TERMINAL_STATES, type JobStatus } from "../../lib/types";

export function useJobPolling(jobId: string | null, onUpdate: (job: JobStatus) => void, onFatal: (message: string) => void) {
  const updateRef = useRef(onUpdate);
  const fatalRef = useRef(onFatal);
  const [connection, setConnection] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => { updateRef.current = onUpdate; fatalRef.current = onFatal; });
  useEffect(() => {
    setConnection("");
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    async function poll() {
      try {
        const job = await requestJson<JobStatus>(`/api/jobs/status?job=${encodeURIComponent(jobId!)}`, { signal: controller.signal }, 15_000);
        if (controller.signal.aborted) return;
        failures = 0;
        setConnection("");
        updateRef.current(job);
        if (TERMINAL_STATES.includes(job.status)) return;
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && [400, 401, 403, 404].includes(error.status)) {
          fatalRef.current(error.message);
          return;
        }
        failures += 1;
        setConnection("Connection interrupted. The worker job may still be running; reconnecting automatically…");
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, Math.min(15_000, 1500 * 2 ** Math.min(failures, 4)));
    }
    void poll(); // Sequential polling: never overlap requests or abandon a job on one network error.
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [jobId, revision]);
  return { connection, reconnect: () => setRevision((value) => value + 1) };
}
