# Independent /model_stat (os.stat) in front of Salad comfyui-api.
# Build/push before applying to klein-bench-001 — do NOT auto-start from this file.
FROM ghcr.io/saladtechnologies/comfyui-api:comfy0.7.0-api1.16.1-torch2.8.0-cuda12.8-runtime

USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY model_stat_lib.py model_stat_server.py entrypoint.sh /opt/container_model_stat/
RUN chmod +x /opt/container_model_stat/entrypoint.sh

# Public port stays 3000; upstream comfyui-api is moved to 3001 by entrypoint.
ENV PUBLIC_PORT=3000 UPSTREAM_PORT=3001
EXPOSE 3000

ENTRYPOINT ["/opt/container_model_stat/entrypoint.sh"]
