# SwiftParcel — Module 4, Assignment 5
Roll number: replace before submission. CPU only. Measurements: 8 November 2026.

## Environment and method
Python 3.12.14, Intel Xeon Platinum 8573C; 3 visible logical CPUs, with a cgroup quota of **2 CPU equivalents**. Host-visible RAM 9.7 GiB; cgroup RAM limit **8 GiB**. Ray is explicitly initialized with 2 CPUs. Requests and servers run on the same machine over loopback, so client overhead and CPU sharing affect capacity. Dependencies are pinned in requirements.txt. Starter eta_data.py and load_test.py are supplied assignment code; implementation and prose were produced with AI assistance, without lecture notebook fragments. Review and disclose this assistance under your course policy.

## A — REST service and measurements
The service loads the selected bundle once, validates all seven features and batch limits, rejects infeasible combinations, preserves order, and emits request IDs and Prometheus metrics. There are 19 REST test instances and 10 pure gate test instances: **29 passed**. Generic inference errors are tested with monkeypatch; no exception internals are returned. Metrics are process-local: the two-worker experiment does not aggregate counters across workers, so a production deployment needs a multiprocess metrics backend. The load generator's “replicas” column counts returned served_by values, which this API does not expose; it is not evidence of worker count.

Single worker, supplied closed-loop load generator, batch 1, four seconds per concurrency:

| Concurrency | Requests/s | p50 ms | p95 ms | p99 ms | Errors |
|---:|---:|---:|---:|---:|---:|
| 1 | 255.0 | 3.6 | 5.9 | 8.6 | 0 |
| 2 | 301.5 | 5.9 | 11.3 | 17.4 | 0 |
| 4 | 305.8 | 11.9 | 21.3 | 28.3 | 0 |
| 8 | 328.8 | 22.6 | 39.6 | 58.0 | 0 |
| 16 | 329.8 | 46.0 | 74.3 | 110.8 | 0 |

Throughput largely flattens by concurrency 8: 328.8 rps, then 329.8 at 16, while p95 rises from 39.6 to 74.3 ms. The highest measured capacity under p95 ≤80 ms is **329.8 rps at concurrency 16**, with zero errors; this is a short-run observed bound, not a long-duration guarantee. Little's Law uses mean response time, not p95: at saturation and 16 outstanding clients, W≈L/λ=16/329.8≈48.5 ms (including client turnaround). Doubling outstanding work from 8 to 16 mostly adds waiting rather than completed requests. Open-loop overload and concurrency above 16 were not measured.

At concurrency 1, 200 timed sequential requests per batch size, mean wall time divided by rows: batch 1 **3.7899 ms/row**, batch 100 **0.0501 ms/row**. Batching amortizes HTTP, JSON, validation and DataFrame setup, and the estimator predicts arrays efficiently; the larger total response time is spread over 100 rows. This measures client-observed cost per row, not isolated estimator CPU time.

Applied change: run Uvicorn with two worker processes to use both CPU equivalents. The hypothesis was roughly twice the capacity by removing the single-process bottleneck; measured results:

| Concurrency | Requests/s | p50 ms | p95 ms | p99 ms | Errors |
|---:|---:|---:|---:|---:|---:|
| 1 | 204.0 | 3.7 | 10.2 | 12.2 | 0 |
| 2 | 335.5 | 5.2 | 10.8 | 15.7 | 0 |
| 4 | 433.0 | 8.5 | 16.2 | 22.0 | 0 |
| 8 | 450.5 | 16.5 | 30.4 | 40.1 | 0 |
| 16 | 449.2 | 33.5 | 61.4 | 79.9 | 0 |

Peak SLO-compliant throughput increased from 329.8 to 450.5 rps, a **1.37× gain**, not 2×. JSON/validation work, contention with the client on the same CPU quota, and process/connection scheduling limit scaling. All measured p95 values remained below 80 ms.

p95 and p99 reveal slow experiences and queueing that the mean hides. A mean can remain acceptable while a significant tail of customers breaches the SLO.

## B — Registry, promotion gate and shadow
Custom pyfunc output is eta_minutes (one decimal) and model_version; registration includes signature, input example, bundled artifact and pinned runtime dependencies, using SQLite.

| Registry version | Alias | Bundle |
|---:|---|---|
| 1 | prod | v1 Ridge |
| 2 | candidate | v2 gradient boosting |

Fresh evaluation uses make_data(2000, seed=99), plus 200 separately timed single-row predictions per alias. Default gate measurements:

| Metric | prod | candidate |
|---|---:|---:|
| Overall MAE, min | 11.9553 | 6.10485 |
| Rush MAE, min | 19.67986 | 8.57951 |
| Rain MAE, min | 11.62274 | 6.28531 |
| Single-row p95, ms | 4.79197 | 4.69933 |

MAE improves by **48.94%**. With default thresholds all four criteria pass and promote=true. With min_rel_gain=0.60, overall_gain=false, the other criteria pass, and promote=false (second-run candidate p95 5.42674 ms). Timing differs between calls; full output is in partB/gate_output.txt. The fresh dataset is the same deterministic seed used by starter training diagnostics; it is not independent of any model selection informed by those diagnostics.

Actual mlflow models serve processes ran on ports 5101 and 5102. Identical first 200 fresh rows were submitted one at a time to both: mean absolute prediction difference **9.4845 minutes**, **35.0%** differ by more than 10 minutes, prod HTTP p95 **17.0379 ms**, candidate HTTP p95 **17.7193 ms**. HTTP latency includes transport/serialization and differs from the gate's in-process timing. An initial launch chose the base interpreter's uvicorn and failed to import MLflow; the retry used the virtual environment's uvicorn and completed all 400 requests.

I would advance v2 to a monitored 10% canary because overall and slice errors improve substantially and the latency gate passes. Shadow disagreement alone cannot establish correctness, but the fresh labelled evaluation supports the change. A running server loads a resolved model artifact at startup, so moving a registry alias does not replace its in-memory model. One way to pick up the new version is a rolling restart behind a load balancer, waiting for readiness before draining each old instance. Another is blue/green deployment: start and warm the new pool, switch traffic atomically, then drain existing requests from the old pool.

## C — Sticky canary
SHA-256 maps customer IDs to a stable uniform bucket in [0,1); candidate routing is bucket < weight, with X-Beta:1 overriding that request. Increasing weight is monotone: every existing candidate stays candidate. The prod deployment has two replicas; candidate autoscaling is 1–3 replicas. Each model replica and router reserves 0.25 CPU: maximum declared CPU demand is 2×0.25 + 3×0.25 + 0.25 = **1.5 CPUs**, within two (Ray system processes still require physical CPU time).

Python hash() is salted across interpreter processes, so restart or replica selection could change assignments. Stickiness keeps the ETA behaviour consistent for a customer's repeat deliveries and avoids mixing treatments within a customer when estimating experimental effects. It also prevents frequent high-volume customers from determining the intended customer-level assignment share, though request share can still differ from customer share.

The candidate target is two ongoing requests per replica, a conservative starting point for short CPU inference batches. An upscale delay of five seconds responds to sustained pressure while avoiding a new replica for every transient spike. A thirty-second downscale delay gives bursts time to settle, and min_replicas=1 avoids cold starts. The cap of three preserves CPU headroom; tune these initial values with actual traffic and queue measurements rather than claiming they are optimal.

Actual 2-CPU Ray verification passed all five assertions: candidate share **0.212** over 1000 distinct IDs (allowed 0.16–0.24); 200 repeat customers retained their arm; those 200 retained their arm after redeploying the identical app; after increasing weight to 0.5 no original candidate moved back to prod; all 50 header overrides used v2. An initial environment startup issue was fixed and the completed verifier exited 0. The exported verify_output.txt retains the five assertion results; verbose internal deployment and authentication-related logs are omitted. These checks establish routing behaviour, not autoscaling performance.

## D — Smoke test and canary aborts
The v1 REST smoke test passed six checks: exact expected version, finite positive ETA, longer-distance sanity, higher-traffic sanity, invalid input returns 422, and p95 ≤80 ms. Observed smoke p95 was **6.19325 ms** over 53 valid requests (three sanity requests and 50 repeats). smoke_eta.py exits 1 on a failed check or exception, and 0 only when all six checks pass.

During a 10% v2 canary, monitor:

| Metric | Abort threshold | Window |
|---|---|---|
| v2 HTTP 5xx + timeout rate | >1% with ≥100 requests | rolling 5 minutes |
| v2 prediction endpoint p95 | >80 ms with ≥100 requests | two consecutive 5-minute windows |
| Labelled v2 MAE / matched prod MAE, overall or rush/rain | >1.05 with ≥200 labelled rows in the evaluated slice | rolling 24 hours after delivery labels arrive |
| Nonfinite or nonpositive ETA rate | >0.1% with ≥1000 predictions | rolling 15 minutes |

Pause release when sample counts are insufficient; do not infer safety from missing labels. Route back to v1 and retain request/version evidence when an abort triggers.

## Verification limits and reproducibility
Not tested: sustained production traffic, external network latency, autoscaler scale-out/down under load, process failures during real rollouts, multiworker Prometheus aggregation, or a separate clean Python 3.10 installation. Timing runs are short single-machine experiments, with no confidence intervals. Models/data/databases are intentionally excluded; regenerate with eta_data.py and registration commands. README.md lists commands; evidence/ contains PNG renderings of captured command output and searchable transcripts, not native desktop screenshots. Pinning captures the tested package versions but does not establish compatibility with every platform.
