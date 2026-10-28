# Self-Hosted Search & Retrieval: SearXNG + Siftdog Integration Guide

This guide documents the architecture, configuration, deployment, and API usage of the self-hosted search and retrieval system integrated into the SAP Knowledge Assistant.

---

## 1. Overview & Architecture

The retrieval system pairs **SearXNG** (for multi-engine web and image metasearch discovery) with **Siftdog** (for high-level search APIs, clean Markdown extraction, bounded web crawling, and site mapping).

```
┌─────────────────────────────────────────────────────────────┐
│                 SAP Knowledge Assistant AI                  │
│     (rag_service / web_search_service / multi_source)       │
└─────────────────────────────┬───────────────────────────────┘
                              │
               UnifiedSearchService (Internal)
       ┌──────────────────────┼──────────────────────┐
       │ (Search, Extract,    │ (Dedicated Image     │ (Cloud Fallback)
       │  Crawl, Map)         │  Search)             │
       ▼                      ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Siftdog    │──────▶│   SearXNG    │       │ Tavily (Opt) │
│ (Port: 8088) │       │ (Port: 8089) │       │              │
└──────────────┘       └──────────────┘       └──────────────┘
```

### Component Roles

1. **SearXNG** (`searxng/searxng:latest`):
   - **Port**: `8089` on host (`127.0.0.1:8089`), internal port `8080` in Docker.
   - **Engines Configured**: Google, DuckDuckGo, Bing, Startpage, Yahoo, Mojeek, Google News, DuckDuckGo News, Google Images, Bing Images, DuckDuckGo Images, GitHub.
   - **Output Format**: JSON API enabled (`format=json`).
   - **Primary Use**: Multi-engine metasearch discovery and visual image retrieval with full metadata (dimensions, image formats, thumbnail URLs, source links).

2. **Siftdog** (`ghcr.io/khsarvar/siftdog:latest`):
   - **Port**: `8088` on host (`127.0.0.1:8088`), internal port `8000` in Docker.
   - **Search Backend**: Connected to SearXNG via Docker network (`SEARXNG_URL=http://searxng:8080`).
   - **Primary Capabilities**:
     - `/search`: Basic and advanced query search with depth, topics, and domain filtering.
     - `/extract`: Clean Markdown and text extraction from target URLs with SSRF protection.
     - `/crawl`: Bounded recursive documentation crawling with path and domain filters.
     - `/map`: Fast sitemap and URL discovery.

3. **UnifiedSearchService** (`backend/app/services/search/unified_service.py`):
   - Central abstraction coordinating search providers.
   - Intelligent failover: Siftdog ➡️ SearXNG ➡️ Tavily ➡️ Internal documentation fallback.
   - Directs image search to SearXNG's dedicated image engines.
   - Automatic passage extraction and SAP authority classification.

---

## 2. Docker Services Configuration

Both services are defined in `docker-compose.yml`:

```yaml
  searxng:
    image: searxng/searxng:latest
    container_name: sap_assistant_searxng
    restart: unless-stopped
    environment:
      SEARXNG_SECRET: ${SEARXNG_SECRET:-searxng-sap-assistant-secret-key-prod-random-token-32b}
    ports:
      - "127.0.0.1:${SEARXNG_HOST_PORT:-8089}:8080"
    volumes:
      - ./docker/searxng/settings.yml:/etc/searxng/settings.yml:ro

  siftdog:
    image: ghcr.io/khsarvar/siftdog:latest
    container_name: sap_assistant_siftdog
    restart: unless-stopped
    depends_on:
      - searxng
    environment:
      SEARXNG_URL: http://searxng:8080
      FETCH_TIMEOUT: ${SIFTDOG_FETCH_TIMEOUT:-15}
      FETCH_CONCURRENCY: ${SIFTDOG_FETCH_CONCURRENCY:-10}
      FETCH_MAX_BYTES: ${SIFTDOG_FETCH_MAX_BYTES:-2097152}
      ALLOW_PRIVATE_NETWORKS: ${SIFTDOG_ALLOW_PRIVATE_NETWORKS:-false}
      CRAWL_MAX_LIMIT: ${SIFTDOG_CRAWL_MAX_LIMIT:-50}
      API_KEYS: ${SIFTDOG_API_KEY:-}
    ports:
      - "127.0.0.1:${SIFTDOG_HOST_PORT:-8088}:8000"
```

### Service Startup & Shutdown

```bash
# Start SearXNG and Siftdog alongside PostgreSQL
docker compose up -d searxng siftdog

# Verify containers are running and healthy
docker ps --filter name=sap_assistant

# View logs for Siftdog or SearXNG
docker logs --tail 50 sap_assistant_siftdog
docker logs --tail 50 sap_assistant_searxng

# Stop services (volumes and database preserved)
docker compose stop searxng siftdog
```

---

## 3. Environment Variables

Configure in `backend/.env`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `WEB_FALLBACK_ENABLED` | `True` | Master switch for external web and visual discovery. |
| `SEARCH_PROVIDER` | `siftdog` | Active search provider (`siftdog`, `searxng`, `tavily`). |
| `SIFTDOG_URL` | `http://127.0.0.1:8088` | Base URL for Siftdog service. |
| `SIFTDOG_API_KEY` | *(optional)* | Optional bearer token for Siftdog authentication. |
| `SEARXNG_URL` | `http://127.0.0.1:8089` | Base URL for SearXNG metasearch instance. |
| `SEARCH_TIMEOUT_SECONDS` | `15.0` | HTTP request timeout in seconds. |
| `SEARCH_MAX_RETRIES` | `2` | Maximum retry attempts on transient network/5xx errors. |
| `SEARCH_FALLBACK_TO_SEARXNG` | `True` | Fallback directly to SearXNG if Siftdog is unavailable. |
| `SEARCH_EXTRACTION_ENABLED` | `True` | Extract clean markdown for search hits missing raw content. |
| `SEARCH_DEFAULT_TOPIC` | `general` | Default search topic (`general` or `news`). |
| `WEB_SEARCH_API_KEY` | *(optional)* | Legacy Tavily API key for tertiary cloud fallback. |

---

## 4. Health Checks

### Check Siftdog Health
```bash
curl http://127.0.0.1:8088/health
# Response: {"status":"healthy"}
```

### Check SearXNG Health & JSON Search
```bash
curl "http://127.0.0.1:8089/search?q=ping&format=json"
```

### Programmatic Python Check
```python
from backend.app.services.search import unified_search_service

# Check Siftdog health
health = unified_search_service.siftdog.check_health()
print("Siftdog health:", health)
```

---

## 5. Usage Examples

### 1. Unified Search (Siftdog with SearXNG Fallback)
```python
from backend.app.services.search import unified_search_service

hits = unified_search_service.search(
    query="SAP BRIM Convergent Invoicing billable items",
    max_results=5,
    include_domains=["help.sap.com", "community.sap.com"],
    include_raw_content=True,
)

for hit in hits:
    print(f"[{hit.score:.2f}] {hit.title} -> {hit.url}")
    if hit.raw_content:
        print(f"Content length: {len(hit.raw_content)} chars")
```

### 2. Dedicated Visual & Diagram Search (SearXNG)
```python
from backend.app.services.search import unified_search_service

images = unified_search_service.search_images(
    query="SAP BRIM architecture process flow diagram",
    max_images=4,
)

for img in images:
    print(f"Image: {img.url}")
    print(f"Thumbnail: {img.thumbnail_url}")
    print(f"Source: {img.source_url} | Resolution: {img.resolution}")
```

### 3. URL Extraction (Siftdog)
```python
from backend.app.services.search import unified_search_service

res = unified_search_service.extract(
    urls=["https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/bp/blocking.html"],
    format="markdown",
)

for page in res.pages:
    print(f"Extracted {page.url} ({len(page.raw_content)} chars)")
for fail in res.failed:
    print(f"Failed {fail.url}: {fail.error}")
```

### 4. Bounded Documentation Crawling (Siftdog)
```python
from backend.app.services.search import unified_search_service

crawl_res = unified_search_service.crawl_site(
    url="https://help.sap.com/docs/SAP_BRIM",
    max_depth=2,
    max_breadth=10,
    limit=20,
    select_paths=["/docs/SAP_BRIM/*"],
)

print(f"Discovered {len(crawl_res.discovered_urls)} documentation pages.")
```

### 5. Fast Site Mapping (Siftdog)
```python
from backend.app.services.search import unified_search_service

map_res = unified_search_service.map_site(
    url="https://help.sap.com/docs/SAP_BRIM",
    max_depth=1,
    limit=50,
)

print(f"Sitemap discovered {len(map_res.urls)} URLs.")
```

---

## 6. Security & SSRF Protection

- **Private Network Blocking**: Siftdog is configured with `ALLOW_PRIVATE_NETWORKS=false`, preventing it from fetching local loopback (`127.0.0.1`), private RFC1918 subnets (`10.0.0.0/8`, `192.168.0.0/16`), or link-local metadata addresses (`169.254.169.254`).
- **Domain Whitelisting**: Searches enforce SAP domain restriction on authoritative properties:
  - `help.sap.com`
  - `learning.sap.com`
  - `community.sap.com`
  - `blogs.sap.com`
  - `sap.com`
- **Safe Schemes Only**: Only absolute `http://` and `https://` URLs are accepted and returned; executable schemes (`javascript:`, `file:`, `data:`) are rejected.
- **Constant-Time Admin Key Verification**: Ingestion and admin routes enforce `hmac.compare_digest` with zero token leakage.

---

## 7. Known Limitations & Notes

1. **Siftdog Image Descriptions**: Siftdog accepts the `include_image_descriptions` parameter but does not generate vision descriptions. The system routes rich image search directly through SearXNG to capture multi-engine image metadata, and uses vision models when image files are uploaded directly.
2. **Upstream Rate Limiting**: SearXNG queries public search engines. `limiter: false` is configured for internal calls between Siftdog and SearXNG, while multi-engine rotation (Google, DuckDuckGo, Bing, Startpage) prevents upstream throttling.
3. **SSRF Guard**: Crawling and extraction of internal/localhost URLs from the host will be rejected by design by Siftdog unless `ALLOW_PRIVATE_NETWORKS=true` is explicitly set in non-production development environments.

---

## 8. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Connection refused on port 8088` | Siftdog container not running | Run `docker compose up -d siftdog` |
| `Connection refused on port 8089` | SearXNG container not running | Run `docker compose up -d searxng` |
| `Siftdog returns empty results` | SearXNG not reachable from inside container | Verify `SEARXNG_URL=http://searxng:8080` in `docker-compose.yml` |
| `422 Unprocessable Entity` | Invalid search parameters | Siftdog strictly validates types; ensure `max_results` is between 1 and 20 |
| `Extraction fails with blocked host` | URL resolves to private or localhost IP | Normal SSRF behavior. Only public URLs can be extracted. |
