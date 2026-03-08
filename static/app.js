const state = {
  defaultSourceDir: "",
  pollers: {},
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "Request failed");
  }
  return data;
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setBadge(id, text, variant = "neutral") {
  const badge = document.getElementById(id);
  if (!badge) {
    return;
  }
  badge.textContent = text;
  badge.className = `badge ${variant}`;
}

function updateHeroSummary(indexStatus, graphStatus, health) {
  const documentNode = document.getElementById("hero-documents");
  const entityNode = document.getElementById("hero-entities");
  const relationNode = document.getElementById("hero-relations");
  const statusNode = document.getElementById("hero-status-copy");

  if (documentNode) {
    documentNode.textContent = `${indexStatus.document_count || 0} PDFs`;
  }
  if (entityNode) {
    entityNode.textContent = graphStatus.entity_count || 0;
  }
  if (relationNode) {
    relationNode.textContent = graphStatus.relation_count || 0;
  }
  if (statusNode) {
    if (!health.kimi_configured) {
      statusNode.textContent = "Kimi 未配置";
    } else if (graphStatus.ready) {
      statusNode.textContent = "图谱可用";
    } else if (indexStatus.ready) {
      statusNode.textContent = "索引可用";
    } else {
      statusNode.textContent = "等待建库";
    }
  }
}

function renderProgress(cardId, progress, dark = false) {
  const card = document.getElementById(cardId);
  if (!card) {
    return;
  }

  const percent = Math.round((progress.progress || 0) * 100);
  const statusText = progress.status === "running"
    ? "运行中"
    : progress.status === "completed"
      ? "已完成"
      : progress.status === "failed"
        ? "失败"
        : "待启动";

  card.innerHTML = `
    <div class="progress-head">
      <strong>${statusText}</strong>
      <span>${percent}%</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" style="width:${percent}%"></div></div>
    <div class="progress-meta">
      <span>阶段：${escapeHtml(progress.stage || "waiting")}</span>
      <span>当前：${escapeHtml(progress.current_item || "-")}</span>
      <span>步数：${progress.completed_steps || 0}/${progress.total_steps || 0}</span>
    </div>
    <p class="progress-copy">${escapeHtml(progress.error || progress.message || "等待操作")}</p>
  `;

  if (dark) {
    card.classList.add("dark-progress");
  }
}

function renderStatus(status) {
  const card = document.getElementById("status-card");
  if (!card) {
    return;
  }

  if (!status.ready) {
    card.innerHTML = `
      <div class="status-empty">
        <strong>索引尚未建立</strong>
        <p>请选择论文目录，完成构建后就可以发起问答。</p>
      </div>
    `;
    return;
  }

  const fileList = (status.files || []).map((file) => `<li>${escapeHtml(file)}</li>`).join("");
  const errorBlock = (status.errors || []).length
    ? `<div class="error-box"><strong>解析告警</strong><p>${status.errors.map(escapeHtml).join("<br />")}</p></div>`
    : "";

  card.innerHTML = `
    <div class="metrics">
      <div><span>Built At</span><strong>${escapeHtml(status.built_at || "-")}</strong></div>
      <div><span>Source Dir</span><strong>${escapeHtml(status.source_dir || "-")}</strong></div>
      <div><span>Documents</span><strong>${status.document_count || 0}</strong></div>
      <div><span>Chunks</span><strong>${status.chunk_count || 0}</strong></div>
    </div>
    <div class="file-list">
      <span>已纳入文件</span>
      <ul>${fileList}</ul>
    </div>
    ${errorBlock}
  `;
}

function renderGraphStatus(status) {
  const card = document.getElementById("graph-status-card");
  if (!card) {
    return;
  }

  const errorBlock = (status.errors || []).length
    ? `<div class="error-box"><strong>状态提醒</strong><p>${status.errors.map(escapeHtml).join("<br />")}</p></div>`
    : "";

  card.innerHTML = `
    <div class="metrics">
      <div><span>Driver</span><strong>${status.driver_available ? "已安装" : "未安装"}</strong></div>
      <div><span>Connected</span><strong>${status.connected ? "已连接" : "未连接"}</strong></div>
      <div><span>Documents</span><strong>${status.document_count || 0}</strong></div>
      <div><span>Entities</span><strong>${status.entity_count || 0}</strong></div>
      <div><span>Relations</span><strong>${status.relation_count || 0}</strong></div>
      <div><span>Built At</span><strong>${escapeHtml(status.last_built_at || "-")}</strong></div>
    </div>
    ${errorBlock}
  `;
}

function formatAnswer(answer) {
  const lines = String(answer || "").replace(/\r/g, "").split("\n");
  const html = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    if (line.startsWith("### ")) {
      closeList();
      html.push(`<h4>${escapeHtml(line.slice(4))}</h4>`);
      continue;
    }

    if (line.startsWith("## ")) {
      closeList();
      html.push(`<h3>${escapeHtml(line.slice(3))}</h3>`);
      continue;
    }

    if (line.startsWith("# ")) {
      closeList();
      html.push(`<h2>${escapeHtml(line.slice(2))}</h2>`);
      continue;
    }

    if (line.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${escapeHtml(line)}</p>`);
  }

  closeList();
  return html.join("");
}

function renderAnswer(answer, isEmpty = false) {
  const node = document.getElementById("answer");
  if (!node) {
    return;
  }

  node.classList.toggle("empty", isEmpty);
  if (isEmpty) {
    node.textContent = answer;
    return;
  }

  node.innerHTML = `<div class="answer-body">${formatAnswer(answer)}</div>`;
}

function renderSources(sources) {
  const container = document.getElementById("sources");
  if (!container) {
    return;
  }

  if (!sources.length) {
    container.innerHTML = '<div class="source-card">暂无来源片段</div>';
    return;
  }

  container.innerHTML = sources.map((source) => `
    <article class="source-card">
      <div class="source-head">
        <strong>[S${source.rank}] ${escapeHtml(source.file_name)}</strong>
        <span>p.${source.page_number} · score ${source.score}</span>
      </div>
      <p>${escapeHtml(source.preview)}</p>
    </article>
  `).join("");
}

function renderGraphFacts(facts) {
  const container = document.getElementById("graph-facts");
  if (!container) {
    return;
  }

  if (!facts.length) {
    container.innerHTML = '<div class="source-card">暂无图谱事实</div>';
    return;
  }

  container.innerHTML = facts.map((fact) => `
    <article class="source-card">
      <div class="source-head">
        <strong>[G${fact.rank}] ${escapeHtml(fact.source)}</strong>
        <span>${escapeHtml(fact.relation)} · ${escapeHtml(fact.document)}</span>
      </div>
      <p>${escapeHtml(fact.source)} (${escapeHtml(fact.source_type)}) → ${escapeHtml(fact.target)} (${escapeHtml(fact.target_type)})</p>
      <p>${escapeHtml(fact.evidence || "无显式证据片段")}</p>
    </article>
  `).join("");
}

async function refreshStatus() {
  const health = await requestJson("/api/health");
  state.defaultSourceDir = health.default_source_dir;

  const sourceInput = document.getElementById("source-dir");
  if (sourceInput && !sourceInput.value) {
    sourceInput.value = health.default_source_dir || "";
  }

  const indexStatus = await requestJson("/api/index/status");
  const graphStatus = await requestJson("/api/graph/status");
  const indexProgress = await requestJson("/api/index/progress");
  const graphProgress = await requestJson("/api/graph/progress");

  if (!health.kimi_configured) {
    setBadge("health-badge", "Kimi 未配置", "warn");
  } else if (indexStatus.ready) {
    setBadge("health-badge", "索引可用", "success");
  } else {
    setBadge("health-badge", "等待建库", "neutral");
  }

  if (graphStatus.ready) {
    setBadge("graph-badge", "图谱可用", "success");
  } else if (!graphStatus.driver_available) {
    setBadge("graph-badge", "缺少驱动", "warn");
  } else if (!graphStatus.connected) {
    setBadge("graph-badge", "未连接", "warn");
  } else {
    setBadge("graph-badge", "待建图", "neutral");
  }

  updateHeroSummary(indexStatus, graphStatus, health);
  renderStatus(indexStatus);
  renderGraphStatus(graphStatus);
  renderProgress("index-progress-card", indexProgress);
  renderProgress("graph-progress-card", graphProgress, true);
}

async function watchProgress(kind, cardId, badgeId) {
  if (state.pollers[kind]) {
    clearInterval(state.pollers[kind]);
  }

  state.pollers[kind] = setInterval(async () => {
    const progress = await requestJson(`/api/${kind}/progress`);
    renderProgress(cardId, progress, kind === "graph");

    if (progress.status === "completed") {
      clearInterval(state.pollers[kind]);
      delete state.pollers[kind];
      setBadge(badgeId, kind === "index" ? "索引可用" : "图谱可用", "success");
      await refreshStatus();
    }

    if (progress.status === "failed") {
      clearInterval(state.pollers[kind]);
      delete state.pollers[kind];
      setBadge(badgeId, kind === "index" ? "建库失败" : "建图失败", "warn");
    }
  }, 1200);
}

async function buildIndex() {
  const payload = {
    source_dir: document.getElementById("source-dir").value.trim(),
    chunk_size: Number(document.getElementById("chunk-size").value),
    overlap: Number(document.getElementById("overlap").value),
  };

  setBadge("health-badge", "建库中", "neutral");
  watchProgress("index", "index-progress-card", "health-badge");

  const status = await requestJson("/api/index/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  renderStatus(status);
}

async function buildGraph() {
  const payload = {
    max_chunks_per_document: Number(document.getElementById("graph-chunks").value),
    max_documents: Number(document.getElementById("graph-docs").value),
  };

  setBadge("graph-badge", "建图中", "neutral");
  watchProgress("graph", "graph-progress-card", "graph-badge");

  const status = await requestJson("/api/graph/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  renderGraphStatus(status);
}

async function uploadFiles(event) {
  event.preventDefault();
  const input = document.getElementById("pdf-files");
  if (!input.files.length) {
    return;
  }

  const formData = new FormData();
  for (const file of input.files) {
    formData.append("files", file);
  }

  await requestJson("/api/upload", {
    method: "POST",
    body: formData,
  });

  input.value = "";
  await refreshStatus();
}

async function askQuestion() {
  const question = document.getElementById("question").value.trim();
  if (!question) {
    return;
  }

  renderAnswer("Kimi 正在整理证据、答案和图谱关系...", true);
  renderSources([]);
  renderGraphFacts([]);

  const response = await requestJson("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      top_k: 5,
      use_graph: document.getElementById("use-graph").checked,
    }),
  });

  renderAnswer(response.answer || "未返回答案");
  renderSources(response.sources || []);
  renderGraphFacts(response.graph_facts || []);
}

function bindPresetQuestions() {
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById("question").value = button.dataset.question || "";
      document.getElementById("question").focus();
    });
  });
}

document.getElementById("build-btn").addEventListener("click", async () => {
  try {
    await buildIndex();
  } catch (error) {
    setBadge("health-badge", "建库失败", "warn");
    renderAnswer(error.message, true);
  }
});

document.getElementById("graph-build-btn").addEventListener("click", async () => {
  try {
    await buildGraph();
  } catch (error) {
    setBadge("graph-badge", "建图失败", "warn");
    renderAnswer(error.message, true);
  }
});

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  try {
    await uploadFiles(event);
  } catch (error) {
    renderAnswer(error.message, true);
  }
});

document.getElementById("ask-btn").addEventListener("click", async () => {
  try {
    await askQuestion();
  } catch (error) {
    renderAnswer(error.message, true);
  }
});

bindPresetQuestions();
refreshStatus().catch((error) => {
  renderAnswer(error.message, true);
  setBadge("health-badge", "初始化失败", "warn");
});