<!-- evalgate:report -->
## evalgate · classify · ❌ FAIL

Run `00000000-0000-7000-8000-000000000000` · mode **offline** · git `unknown` · 60 cases · created 2026-10-16T00:00:00Z
Paired bootstrap: 10,000 resamples, seed 1337, max regression 1.0 pp, baseline `00000000-0000-7000-8000-000000000000`

| Metric | Value | 95% CI | Threshold | Baseline | Δ (pp) | 95% CI of Δ (pp) | Gate | Mode |
|---|---:|---|---:|---:|---:|---|---|---|
| `label_accuracy` | 0.7667 | [n/a, n/a] | ≥ 0.90 | 0.9000 | -13.33 | [-21.67, -5.00], n=60 | ❌ fail | offline |
| `label_format` | 1.0000 | [n/a, n/a] | ≥ 0.90 | 1.0000 | +0.00 | [+0.00, +0.00], n=60 | off | offline |

**Cost** USD 0.0042 total, USD 0.000070 per case (offline), budget USD 0.5 · **Latency** p50 50 ms, p95 100 ms (offline), budget p95 800 ms

### Gate failures

- **threshold** `label_accuracy`: value 0.7667 vs limit 0.9000 (offline)
- **regression** `label_accuracy`: -13.33 pp vs baseline (95% CI -21.67 to -5.00 pp), 0.9000 → 0.7667 (offline)

### Worst cases (10 of 14 failed)

| Case | Scores | Error |
|---|---|---|
| `c-0000` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0001` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0002` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0003` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0004` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0005` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0006` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0007` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0054` | label\_accuracy 0.00, label\_format 1.00 |  |
| `c-0055` | label\_accuracy 0.00, label\_format 1.00 |  |

<sub>evalgate report.v1 · classify · mode offline</sub>
