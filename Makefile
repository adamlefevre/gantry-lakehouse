SHELL := /bin/bash
-include .env
export

# Public demo bucket (open CORS, NYC Taxi sample only). Keep telemetry out of it.
DEMO_BUCKET_NAME ?= gantry-demo

.PHONY: help init-bucket cors ingest compact test modal-test modal-deploy clean demo-init demo-ingest

help:
	@echo "gantry-lakehouse commands:"
	@echo "  make init-bucket  - Provision the R2 bucket via Wrangler"
	@echo "  make cors         - Apply CORS policy to the R2 bucket"
	@echo "  make ingest       - Stream NYC Taxi parquet sample into R2 via DuckDB"
	@echo "  make compact      - Run partition bin-packing & compaction locally"
	@echo "  make test         - Run ephemeral integration tests"
	@echo "  make modal-test   - Run scheduled compaction once on Modal (real bucket; deletes source files)"
	@echo "  make modal-deploy - Deploy the daily compaction cron to Modal"
	@echo "  make clean        - Delete the R2 bucket"
	@echo "  make demo-init    - Create the public demo bucket and apply open CORS"
	@echo "  make demo-ingest  - Ingest the NYC Taxi sample into the demo bucket"

init-bucket:
	@echo "==> Creating R2 bucket: $(R2_BUCKET_NAME)..."
	npx wrangler r2 bucket create $(R2_BUCKET_NAME)

cors:
	@echo "==> Setting open CORS policy for DuckDB-Wasm / client read access..."
	@echo '{"rules":[{"allowed":{"origins":["*"],"methods":["GET","HEAD"],"headers":["*"]},"exposeHeaders":["Content-Range","Content-Length","Accept-Ranges","ETag"],"maxAgeSeconds":3600}]}' > .cors.json
	npx wrangler r2 bucket cors set $(R2_BUCKET_NAME) --file .cors.json --force
	@rm -f .cors.json

ingest:
	@echo "==> Ingesting partition-pruned dataset into r2://$(R2_BUCKET_NAME)..."
	python pipelines/ingest.py

compact:
	@echo "==> Running partition compaction on r2://$(R2_BUCKET_NAME)..."
	python pipelines/compact.py

test:
	@echo "==> Running lakehouse integration test suite..."
	pytest tests/test_compaction.py -v -s

modal-test:
	@echo "==> Running scheduled compaction once on Modal (real bucket)..."
	modal run jobs/scheduled_compaction.py

modal-deploy:
	@echo "==> Deploying daily scheduled compaction job to Modal..."
	modal deploy jobs/scheduled_compaction.py

clean:
	@echo "==> Deleting R2 bucket: $(R2_BUCKET_NAME)..."
	npx wrangler r2 bucket delete $(R2_BUCKET_NAME)

demo-init:
	$(MAKE) init-bucket cors R2_BUCKET_NAME=$(DEMO_BUCKET_NAME)

# Uses the demo-only token (DEMO_R2_*) so the factory's keys never touch the public bucket.
demo-ingest:
	$(MAKE) ingest R2_BUCKET_NAME=$(DEMO_BUCKET_NAME) R2_ACCESS_KEY_ID=$(DEMO_R2_ACCESS_KEY_ID) R2_SECRET_ACCESS_KEY=$(DEMO_R2_SECRET_ACCESS_KEY)
