# CropRAG Portfolio

闈㈠悜 AI 搴旂敤寮€鍙戞眰鑱屾柟鍚戠殑浣滃搧闆嗛」鐩紝鍩轰簬鐪熷疄鍐滀綔鐗╁垎绫昏鏂?PDF 瀹屾垚鏂囨。瑙ｆ瀽銆丷AG 闂瓟銆佸疄浣撴娊鍙栧拰 Neo4j 鍥捐氨澧炲己銆?
## Stack

- Backend: FastAPI
- LLM: Kimi (Anthropic-compatible API)
- Retrieval: Pure Python TF-IDF sparse retrieval
- Graph: Neo4j local harness
- Frontend: Vanilla HTML/CSS/JS portfolio page

## Data

- Source directory: `E:\crop_paper\鍐滀綔鐗╁垎绫昏鏂嘸
- Indexed PDFs: `17`
- Current graph snapshot: `17` documents, `259` entities, `662` relations

## Run App

```powershell
cd D:\鏂囨。\Playground\project-3-kimi-rag-mvp
$env:ANTHROPIC_BASE_URL='https://api.kimi.com/coding/'
$env:ANTHROPIC_AUTH_TOKEN=''
$env:ANTHROPIC_API_KEY='your-kimi-key'
$env:NEO4J_URI='bolt://localhost:7687'
$env:NEO4J_AUTH_ENABLED='false'
python app.py
```

Neo4j harness stores data in-memory. If you restart it, run `POST /api/graph/build` again to reload the graph.`r`n`r`n## Start Neo4j

```powershell
cd D:\鏂囨。\Playground\project-3-kimi-rag-mvp\runtime
powershell -ExecutionPolicy Bypass -File .\start_neo4j_harness.ps1
```

Stop it with:

```powershell
cd D:\鏂囨。\Playground\project-3-kimi-rag-mvp\runtime
powershell -ExecutionPolicy Bypass -File .\stop_neo4j_harness.ps1
```

## APIs

- `GET /api/health`
- `GET /api/index/status`
- `GET /api/index/progress`
- `GET /api/graph/status`
- `GET /api/graph/progress`
- `POST /api/index/build`
- `POST /api/graph/build`
- `POST /api/graph/search`
- `POST /api/chat`

## Portfolio Assets

- `docs/PORTFOLIO_GUIDE.md`
- `docs/screenshots/overview.svg`
- `docs/screenshots/workspace.svg`
- `docs/screenshots/architecture.svg`