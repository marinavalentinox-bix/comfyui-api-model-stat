# Exposing GET /model_stat

## Mechanism
- `model_stat_server.py` serves `GET /model_stat` JSON: exists / path / size / readable / optional head_sha256 / tail_sha256 per required model file.
- Stats use pure `os.stat` + open(read 1) inside the container — **never** Salad `/download`.

## Runtime wiring (entrypoint.sh)
1. Start upstream comfyui-api on `127.0.0.1:3001` (not public).
2. Start `model_stat_server` in reverse-proxy mode on `0.0.0.0:3000`:
   - `/model_stat` → local os.stat handler
   - everything else → proxy to `127.0.0.1:3001`

Salad’s container port remains **3000**, so DNS paths like `/prompt`, `/ready`, `/download` keep working; `/model_stat` is additive.

## Deploy (prepare only — do not start replicas without GO)
```bash
# from salad_bench/container_model_stat
docker build -t <registry>/comfyui-api-model-stat:<tag> .
docker push <registry>/comfyui-api-model-stat:<tag>
# then PATCH container group image; keep replicas=0 / autostart=false until GO
```

## Client
`gate.probe_files` → `make_http_model_stat_fn` → `GET https://<dns>/model_stat`.
`/download` is advisory after success only; never required for first `files_verified`.
