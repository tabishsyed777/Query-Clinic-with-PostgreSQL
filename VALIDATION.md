# Verification

Tested with Docker and PostgreSQL 16 in the development environment.

- `docker compose run --rm --no-deps web pytest -q -p no:cacheprovider`: **20 passed**.
- Live HTTP checks passed for the dashboard, database health, all three benchmarks, and saved history.
- Dashboard JavaScript syntax passed `node --check`.
- A browser visual/interaction test has not been performed.

One observed five-sample warm-cache run:

| Query | Before median | After median | Ratio | Results match |
| --- | ---: | ---: | ---: | --- |
| Customer history | 4.207 ms | 0.055 ms | 76.49× | Yes |
| Daily paid revenue | 4.310 ms | 0.156 ms | 27.63× | Yes |
| Pending queue | 7.448 ms | 0.030 ms | 248.27× | Yes |

These are local synthetic-data measurements, not guaranteed speedups. Full JSON evidence is generated under `work/benchmark-evidence.json` and is also available through saved runs in the app.

The managed environment required a trusted CA bundle during Docker dependency installation. The image was built with:

```bash
docker build --secret id=pip_ca,src=/etc/ssl/certs/ca-certificates.crt -t query-clinic-web .
docker compose up -d --no-build
```

The optional BuildKit secret supplies CA trust only during the build; it is not copied into the image. Standard environments can use the documented Compose build directly. TLS verification was retained.

One dependency emitted a TestClient deprecation warning; no tests failed. GitHub CI runs the PostgreSQL test suite on pushes and pull requests; see the repository Actions tab for its current status.
